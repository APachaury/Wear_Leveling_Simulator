## @file flash_memory.py
## @brief Core implementation of the flash memory system.
## @details This module implements the fundamental components of flash memory: pages, blocks,
## and the main memory controller. It handles the low-level operations of reading,
## writing, and erasing data while tracking wear levels and memory status.

# Required imports for numerical operations and type hinting
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import config
from enum import Enum

class PageState(Enum):
    ##
    # @brief Represents the possible states of a flash memory page
    ##
    ERASED = 0
    PROGRAMMED = 1
    INVALID = 2
    DEAD = 3

@dataclass
class Page:
    ##
    # @brief Represents a single page in flash memory.
    # A page is the smallest unit that can be programmed.
    ##
    
    state: PageState = PageState.ERASED # Current state of page
    data: Optional[bytes] = None # Data stored in page (None if erased)
    pe_cycles: int = 0 # Number of program/erase cycles page has undergone
    last_write_time: int = 0 # Timestamp of when page was last written
    last_moved_time: int = 0 # Timestamp of when page's data was last moved for wear leveling

class Block:
    ##
    # @brief Represents a block of pages in flash memory.
    # A block is the smallest unit that can be erased in flash memory.
    # Multiple pages are grouped into a block for efficient erasure operations.
    ##
    def __init__(self, block_id: int) -> None:
        ##
        # @brief Initialize a new block with a given ID.
        #
        # @param block_id Unique identifier for this block
        ##
        
        self.block_id = block_id # Store the block's identifier
        self.pages = [Page() for _ in range(config.PAGES_PER_BLOCK)] # Create a list of empty pages for this bloc
        self.erase_count = 0 # Counter for how many times this block has been erased
        self.valid_pages_count = config.PAGES_PER_BLOCK # Track how many pages in this block contain valid data
        self.last_operation_number = 0 # Track when this block was last used (in terms of operations, not wall clock time)
        self.last_operation_time = 0 # Track when this block was last used (in terms of simulation time)
        
    def was_recently_active(self, current_operation: int) -> bool:
        ##
        # @brief Check if block has been accessed recently based on operation count.
        #
        # @param current_operation Current operation count to compare against
        # @return bool True if block was recently active
        ##
        # Use operation-based activity check
        return (current_operation - self.last_operation_number) < config.ACTIVITY_WINDOW

    def erase(self, operation_number: int) -> bool:
        ##
        # @brief Erase all non-dead pages in the block. Dead pages remain untouched.
        #
        # @param operation_number Current operation number in simulation
        # @return bool True if at least one page was erased successfully, False if all pages are dead
        ##
        # Check if all pages in the block are dead
        if all(page.state == PageState.DEAD for page in self.pages):
            print(f"All pages in block {self.block_id} are dead")
            return True
        
        # Check if block has exceeded its P/E cycle limit
        if self.erase_count >= config.MAX_PE_CYCLES_FOR_ENDURANCE:
            for page in self.pages:
                page.state = PageState.DEAD
            print(f"Block {self.block_id} has exceeded its P/E cycle limit")
            return True
            
        # Increment the block's erase counter
        self.erase_count += 1
        
        # Update activity time
        self.last_operation_number = operation_number
        
        # Reset all non-dead pages in the block
        pages_erased = 0
        for page in self.pages:
            if page.state != PageState.DEAD:
                page.data = None  # Clear the data
                page.pe_cycles += 1  # Increment P/E cycle count
                page.state = PageState.ERASED
                pages_erased += 1
                
                # Check if page has exceeded its lifetime
                if page.pe_cycles >= config.MAX_PE_CYCLES_FOR_ENDURANCE:
                    page.state = PageState.DEAD
                    
        return pages_erased > 0

class FlashAddressError(Exception):
    ##
    # @brief Exception raised for invalid flash memory addresses.
    ##
    pass

class FlashMemory:
    ##
    # @brief Main flash memory system.
    # Manages all blocks and provides interface for read/write operations.
    # Also tracks overall memory health and statistics.
    ##
    def __init__(self) -> None:
        ##
        # @brief Initialize the flash memory with empty blocks.
        ##
        self.blocks = [Block(i) for i in range(config.PHYSICAL_BLOCKS)]
        
        # Counter for total number of dead pages
        self.dead_pages_count = 0
        
        # Track history of dead pages over time
        # Each entry is (time, number_of_dead_pages)
        self.history = []
        
        # Counter for operations performed on this flash memory.
        # Used instead of wall clock time because:
        # 1. Flash wear depends on operations, not time
        # 2. Helps track block/page access patterns
        # 3. Makes simulation behavior consistent
        self.operation_count = 0
        
        # Track simulation time separately from operation count
        self.simulation_time = 0
        
    def write(self, block_id: int, page_id: int, data: bytes) -> bool:
        ##
        # @brief Write data to a specific page.
        #
        # @param block_id ID of block to write to
        # @param page_id ID of page within block
        # @param data Data to write
        # @return bool True if write was successful
        # @throws FlashAddressError If block or page ID is invalid
        ##
        # Validate block and page IDs
        if not (0 <= block_id < config.PHYSICAL_BLOCKS and 0 <= page_id < config.PAGES_PER_BLOCK):
            raise FlashAddressError("Invalid block or page ID")
            
        # Get block and page
        block = self.blocks[block_id]
        page = block.pages[page_id]
        
        # Check if page is writable
        if page.state not in [PageState.ERASED]:
            return False
            
        # Write data
        page.data = data
        page.state = PageState.PROGRAMMED
        page.last_write_time = self.simulation_time
        
        # Update block's last access time
        block.last_operation_number = self.operation_count
        block.last_operation_time = self.simulation_time
        
        # Increment operation count - do this AFTER updating timestamps
        self.operation_count += 1
        
        return True

    def read(self, block_id: int, page_id: int) -> Optional[bytes]:
        ##
        # @brief Read data from a specific page.
        #
        # @param block_id ID of block to read from
        # @param page_id ID of page within block
        # @return Optional[bytes] Data read from page, or None if read failed
        # @throws FlashAddressError If block or page ID is invalid
        ##
        # Validate block and page IDs
        if not (0 <= block_id < config.PHYSICAL_BLOCKS and 0 <= page_id < config.PAGES_PER_BLOCK):
            raise FlashAddressError("Invalid block or page ID")
            
        # Get block and page
        block = self.blocks[block_id]
        page = block.pages[page_id]
        
        # Check if page contains valid data
        if page.state != PageState.PROGRAMMED:
            return None
            
        # Update block's last access time
        block.last_operation_number = self.operation_count
        block.last_operation_time = self.simulation_time
        
        # Increment operation count - do this AFTER updating timestamps
        self.operation_count += 1
        
        return page.data

    def invalidate_page(self, block_id: int, page_id: int) -> None:
        ##
        # @brief Invalidate a specific page.
        #
        # @param block_id Block ID containing the page
        # @param page_id Page ID to invalidate
        # @throws FlashAddressError If block or page ID is invalid
        ##
        if block_id >= config.PHYSICAL_BLOCKS:
            raise FlashAddressError(f"Block ID {block_id} exceeds maximum block ID {config.PHYSICAL_BLOCKS-1}")
            
        if page_id >= config.PAGES_PER_BLOCK:
            raise FlashAddressError(f"Page ID {page_id} exceeds maximum page ID {config.PAGES_PER_BLOCK-1}")
            
        page = self.blocks[block_id].pages[page_id]
        page.state = PageState.INVALID
        page.data = None

    def erase_block(self, block_id: int) -> bool:
        ##
        # @brief Erase a specific block.
        #
        # @param block_id ID of block to erase
        # @return bool True if erase was successful
        # @throws FlashAddressError If block ID is invalid
        ##
        # Validate block ID
        if not 0 <= block_id < config.PHYSICAL_BLOCKS:
            raise FlashAddressError("Invalid block ID")
            
        # Get block
        block = self.blocks[block_id]
        
        # Update block's last access time before attempting erase
        block.last_operation_time = self.simulation_time
        
        # Try to erase the block using current operation count
        if block.erase(self.operation_count):
            # Increment operation count - do this AFTER updating timestamps
            self.operation_count += 1
            return True
            
        return False

    def get_block_status(self, block_id: int) -> Dict:
        ##
        # @brief Get detailed status information for a specific block.
        #
        # @param block_id ID of block to check
        # @return Dict containing block statistics
        ##
        block = self.blocks[block_id]
        return {
            'erase_count': block.erase_count,
            'valid_pages': block.valid_pages_count,
            'dead_pages': sum(1 for page in block.pages if page.state == PageState.DEAD),
            'invalid_pages': sum(1 for page in block.pages if page.state == PageState.INVALID),
            'erased_pages': sum(1 for page in block.pages if page.state == PageState.ERASED),
            'programmed_pages': sum(1 for page in block.pages if page.state == PageState.PROGRAMMED)
        }
