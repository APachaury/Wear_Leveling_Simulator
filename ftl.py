## @file ftl.py
## @brief Flash Translation Layer (FTL) implementation.
## @details This module implements the Flash Translation Layer, which manages the mapping between
## logical addresses (used by the host) and physical addresses (actual flash memory locations).
## The FTL also handles both static and dynamic wear leveling, and garbage collection
## to optimize flash memory usage and lifetime.

from typing import Dict, Optional, List, Set, Tuple
import config
from flash_memory import FlashMemory, FlashAddressError
from wear_leveling import WearLeveling
from enum import Enum

class PageState(Enum):
    ##
    # @brief Enumerates the possible states of a page.
    ##
    DEAD = 1
    ERASED = 2
    PROGRAMMED = 3
    INVALID = 4

class FTLAddressError(Exception):
    ##
    # @brief Exception raised for invalid FTL addresses.
    ##
    pass

class FTL:
    ##
    # @brief Flash Translation Layer managing logical to physical address mapping.
    #
    # The FTL is responsible for:
    # 1. Address translation (logical to physical)
    # 2. Garbage collection
    # 3. Dynamic wear leveling (during page allocation)
    # 4. Static wear leveling coordination (periodic data movement)
    # 5. Managing free pages
    ##
    def __init__(self, flash_memory: FlashMemory, wear_leveling: Optional[WearLeveling] = None) -> None:
        ##
        # @brief Initialize the FTL.
        #
        # @param flash_memory Reference to the flash memory system
        # @param wear_leveling Optional wear leveling controller (for static wear leveling)
        ##
        
        self.flash_memory = flash_memory
        self.wear_leveling = wear_leveling  # this is an object
        self.wear_leveling_enabled = wear_leveling is not None  # this is a bool data type
        
        # Initialize fixed-size mapping table (logical to physical)
        self.logical_to_physical = list(range(config.LOGICAL_PAGES))
        
        # Initialize free pages as a set for O(1) operations
        self.free_pages = set(range(config.PHYSICAL_PAGES))
        
        # Initialize free blocks as a set for O(1) operations
        self.free_blocks = set(range(config.PHYSICAL_BLOCKS))
        
        # Track block wear levels for dynamic wear leveling
        self.block_wear_levels = [0] * config.PHYSICAL_BLOCKS
        
        # Note: We no longer maintain our own operation counter
        # All operation counting is handled by flash_memory

    def validate_logical_address(self, logical_addr: int) -> None:
        ##
        # @brief Validate a logical address.
        #
        # @param logical_addr Logical address to validate
        # @throws FTLAddressError If address is invalid
        ##
        if not 0 <= logical_addr < config.LOGICAL_PAGES:
            raise FTLAddressError(f"Logical address {logical_addr} exceeds maximum logical address {config.LOGICAL_PAGES-1}")

    def validate_physical_address(self, physical_addr: int) -> None:
        ##
        # @brief Validate a physical address.
        #
        # @param physical_addr Physical address to validate
        # @throws FTLAddressError If address is invalid
        ##
        if not 0 <= physical_addr < config.PHYSICAL_PAGES:
            raise FTLAddressError(f"Physical address {physical_addr} exceeds maximum physical address {config.PHYSICAL_PAGES-1}")

    def update_block_free_status(self, block_id: int) -> None:
        ##
        # @brief Update the free status of a block based on its pages.
        #
        # @param block_id The block ID to check and update
        ##
        # Check if block has any free pages
        start_addr = block_id * config.PAGES_PER_BLOCK
        end_addr = start_addr + config.PAGES_PER_BLOCK
        
        has_free_pages = False
        for addr in range(start_addr, end_addr):
            if addr in self.free_pages:
                has_free_pages = True
                break
        
        # Update free_blocks set
        if has_free_pages:
            self.free_blocks.add(block_id)
        else:
            self.free_blocks.discard(block_id)

    def sync_block_wear_level(self, block_id: int) -> None: 
        ##
        # @brief Update the tracked wear level for a block.
        # Uses the block's erase count as a measure of wear.
        #
        # @param block_id ID of the block to update
        #
        # We track wear in the memory using block erase cycles, not page program cycles.
        # Both operations cause wear, but erase cycles are more destructive than programming (writing) cycles.
        # The erase operation requires applying a higher voltage across all cells simultaneously, which makes it more destructive.
        # If we want to program a logic 1, we don't even have to change anything, since when a block is erased, 
        # all the cells are reset to no charge in the FTL, which represents logic 1.
        # Flash memory manufacturers generally specify P/E limits per block, not per page, 
        # since the destructive erase operation is done on the whole block.
        # We need to focus on minimizing erase operations throughout the simulation.
        ##
        status = self.flash_memory.get_block_status(block_id)
        self.block_wear_levels[block_id] = status['erase_count']

    def get_free_blocks(self) -> Set[int]:
        ##
        # @brief Get set of blocks that have at least one free page.
        #
        # @return Set[int] Set of block IDs with free pages
        ##
        return {page // config.PAGES_PER_BLOCK for page in self.free_pages}
        # This is a set comprehension that creates a set of block numbers that have free pages:
        # 1. Iterates through each page number in self.free_pages
        # 2. For each page, calculates its block number using floor division (//)
        #    Example: if PAGES_PER_BLOCK = 64:
        #    - Page 100 → Block 1 (100 // 64 = 1)
        #    - Page 102 → Block 1 (102 // 64 = 1)
        #    - Page 500 → Block 7 (500 // 64 = 7)
        # 3. Creates a set of these block numbers (duplicates automatically removed)
        #    Result from example: {1, 7}

    def get_free_page(self) -> Optional[int]:
        ##
        # @brief Get next available free page for writing using dynamic wear leveling.
        # Selects a page from one of the least worn blocks to balance wear.
        #
        # @return Optional[int] Physical page address if available, None if no free pages
        ##
        if not self.free_pages:
            return None

        # Get blocks that have free pages
        free_blocks = self.get_free_blocks()
        if not free_blocks:
            return None

        # Update wear levels for all free blocks
        for block_id in free_blocks:
            self.sync_block_wear_level(block_id)

        # Find minimum wear level among free blocks
        min_wear = min(self.block_wear_levels[block_id] for block_id in free_blocks)

        # Get all blocks within acceptable wear range
        candidate_blocks = {
            block_id for block_id in free_blocks
            if self.block_wear_levels[block_id] <= min_wear + config.DYNAMIC_WEAR_WINDOW
        }

        # Select the first free page from any of the candidate blocks
        for page in self.free_pages:
            block_id = page // config.PAGES_PER_BLOCK
            if block_id in candidate_blocks:
                self.free_pages.discard(page)
                return page

        # The logic being used above to have a set of candidate blocks and select one free page
        # is likely not optimal. We should polish this later, not doing it now for simplicity.

        return None

    def write(self, logical_addr: int, data: bytes) -> bool:
        ##
        # @brief Main entry point for writes
        #
        # @param logical_addr Logical address to write to
        # @param data Data to write
        # @return bool True if write succeeded
        ##
        if self.wear_leveling_enabled:
            return self._write_with_dynamic_wear_leveling(logical_addr, data)
        else:
            return self.write_without_wear_leveling(logical_addr, data)

    def _write_with_dynamic_wear_leveling(self, logical_addr: int, data: bytes) -> bool:
        ##
        # @brief Write with dynamic wear leveling strategy
        #
        # @param logical_addr Logical address to write to
        # @param data Data to write
        # @return bool True if write succeeded
        # @throws Exception If no free pages available after garbage collection
        ##
        self.validate_logical_address(logical_addr)
        # Check if current page needs invalidation
        current_physical = self.logical_to_physical[logical_addr]
        if self.is_page_programmed(current_physical):
            self.invalidate_page(current_physical)
            
        # Get a new page using dynamic wear leveling
        physical_addr = self.get_page_with_wear_leveling()
        if physical_addr is None:
            # Try garbage collection
            if self.garbage_collect():
                physical_addr = self.get_page_with_wear_leveling()
            if physical_addr is None:
                raise Exception("No free pages available after garbage collection. The system is out of space.")
                
        # Write data
        if self.write_to_physical(physical_addr, data):
            self.logical_to_physical[logical_addr] = physical_addr
            # Update wear tracking after write
            block_id = physical_addr // config.PAGES_PER_BLOCK
            self.sync_block_wear_level(block_id)
            # Note: operation_count is now managed by FlashMemory
            return True
            
        return False

    def move_data_for_wear_leveling(self, source_logical: int, target_logical: int) -> bool:
        ##
        # @brief Move data from one logical address to another.
        # This is the core function for data movement in wear leveling.
        #
        # @param source_logical Source logical address
        # @param target_logical Target logical address
        # @return bool True if move succeeded
        # @throws FTLAddressError If addresses are invalid
        ##
        self.validate_logical_address(source_logical)
        self.validate_logical_address(target_logical)
            
        # Get source data
        source_physical = self.logical_to_physical[source_logical]
        source_block, source_page = self.get_block_and_page_ids(source_physical)
        
        try:
            data = self.flash_memory.read(source_block, source_page)
        except FlashAddressError as e:
            raise FTLAddressError(f"Invalid source address: {e}")
            
        if data is None:
            return False
            
        # Check target location
        target_physical = self.logical_to_physical[target_logical]
        if target_physical not in self.free_pages:
            return False
            
        # Write to target
        target_block, target_page = self.get_block_and_page_ids(target_physical)
        try:
            if self.flash_memory.write(target_block, target_page, data):
                # Update free pages tracking
                self.free_pages.discard(target_physical)
                
                # Update mapping
                self.logical_to_physical[target_logical] = target_physical
                
                # Invalidate old page
                self.invalidate_page(source_physical)
                
                return True
        except FlashAddressError as e:
            raise FTLAddressError(f"Invalid target address: {e}")
            
        return False

    def swap_pages_for_wear_leveling(self, logical_addr1: int, logical_addr2: int) -> bool:
        ##
        # @brief Swap data between two logical addresses.
        # Uses move_data_for_wear_leveling to perform the swap via a temporary page.
        #
        # @param logical_addr1 First logical address
        # @param logical_addr2 Second logical address
        # @return bool True if swap succeeded
        # @throws FTLAddressError If addresses are invalid
        ##
        self.validate_logical_address(logical_addr1)
        self.validate_logical_address(logical_addr2)
        
        # Find a free page to use as temporary storage
        temp_physical = self.get_free_page()
        if temp_physical is None:
            return False
            
        # Convert to logical address for move operation
        # enumerate(self.logical_to_physical) generates pairs of (logical, physical)
        # we loop over these pairs until we find the pair where physical matches temp_physical
        # then we set temp_logical to the corresponding logical address
        temp_logical = None
        for logical, physical in enumerate(self.logical_to_physical):
            if physical == temp_physical:
                temp_logical = logical
                break
                
        if temp_logical is None:
            return False
            
        # Perform the three-way move
        try:
            # Move addr1 → temp
            if not self.move_data_for_wear_leveling(logical_addr1, temp_logical):
                return False
                
            # Move addr2 → addr1
            if not self.move_data_for_wear_leveling(logical_addr2, logical_addr1):
                # The code implements partial rollbacks if any of these 3 steps fail
                # We reset the previous move back to how it was and return false
                self.move_data_for_wear_leveling(temp_logical, logical_addr1)
                return False
                
            # Move temp → addr2
            if not self.move_data_for_wear_leveling(temp_logical, logical_addr2):
                # Same rollback as above
                self.move_data_for_wear_leveling(logical_addr1, logical_addr2)
                self.move_data_for_wear_leveling(temp_logical, logical_addr1)
                return False
                
            return True
            
        except FTLAddressError:
            # If any move fails with an address error, the state might be inconsistent
            # In a production system, we would need a proper rollback mechanism
            raise

    def write_without_wear_leveling(self, logical_addr: int, data: bytes) -> bool:
        ##
        # @brief Write without any wear leveling
        #
        # @param logical_addr Logical address to write to
        # @param data Data to write
        # @return bool True if write succeeded
        ##
        self.validate_logical_address(logical_addr)
        # Check if current page needs invalidation
        current_physical = self.logical_to_physical[logical_addr]
        if self.is_page_programmed(current_physical):
            self.invalidate_page(current_physical)
            
        # Get next free page
        physical_addr = self.get_next_free_page()
        if physical_addr is None:
            # Try garbage collection
            if self.garbage_collect():
                physical_addr = self.get_next_free_page()
            if physical_addr is None:
                raise Exception("No free pages available. Garbage collection either failed or did not free enough space.")
                
        # Write data
        if self.write_to_physical(physical_addr, data):
            self.logical_to_physical[logical_addr] = physical_addr
            # Note: operation_count is now managed by FlashMemory
            return True
            
        return False

    def get_page_with_wear_leveling(self) -> Optional[int]:
        ##
        # @brief Get next page using dynamic wear leveling strategy
        #
        # @return Optional[int] Physical page address if available, None if no free pages
        ##
        if not self.free_pages:
            return None

        if not self.free_blocks:
            return None

        # Update wear levels
        for block_id in self.free_blocks:
            self.sync_block_wear_level(block_id)

        # Find least worn blocks
        min_wear = min(self.block_wear_levels[block_id] for block_id in self.free_blocks)
        candidates = {
            block_id for block_id in self.free_blocks
            if self.block_wear_levels[block_id] <= min_wear + config.DYNAMIC_WEAR_WINDOW
        }

        # Get first free page from candidate blocks
        for page in self.free_pages:
            if page // config.PAGES_PER_BLOCK in candidates:
                self.free_pages.discard(page)
                return page

        return None

    def get_next_free_page(self) -> Optional[int]:
        ##
        # @brief Get next free page without wear leveling
        #
        # @return Optional[int] Physical page address if available, None if no free pages
        ##
        if not self.free_pages:
            return None
        page = min(self.free_pages)  # Get first available page
        self.free_pages.discard(page)
        return page

    def is_page_programmed(self, physical_addr: int) -> bool:
        ##
        # @brief Check if a page contains valid data
        #
        # @param physical_addr Physical address to check
        # @return bool True if page is programmed
        ##
        block_id, page_id = self.get_block_and_page_ids(physical_addr)
        return self.flash_memory.blocks[block_id].pages[page_id].state == PageState.PROGRAMMED

    def invalidate_page(self, physical_addr: int):
        ##
        # @brief Invalidate a page and update free pages set
        #
        # @param physical_addr Physical address to invalidate
        ##
        self.flash_memory.invalidate_page(physical_addr)
        self.free_pages.discard(physical_addr)
        
        # Update free blocks status
        block_id = physical_addr // config.PAGES_PER_BLOCK
        self.update_block_free_status(block_id)

    def write_to_physical(self, physical_addr: int, data: bytes) -> bool:
        ##
        # @brief Write data to a physical address in flash memory.
        #
        # This method handles the actual writing to flash memory and manages free pages tracking.
        # When called, the physical_addr has typically already been removed from free_pages
        # by methods like get_next_free_page() or get_page_with_wear_leveling().
        #
        # @param physical_addr Physical address to write to
        # @param data Data bytes to write
        # @return bool True if write was successful, False otherwise
        ##
        self.validate_physical_address(physical_addr)
        block_id, page_id = self.get_block_and_page_ids(physical_addr)
        
        # Attempt to write data to flash memory hardware
        success = self.flash_memory.write(block_id, page_id, data)
        
        if success:
            # Write succeeded - ensure page is not in free_pages as it's now PROGRAMMED
            self.free_pages.discard(physical_addr)
            # Update block status as it may no longer have free pages
            self.update_block_free_status(block_id)
        else:
            # Write failed - page remains in ERASED state and is still usable
            # Add it back to free_pages to ensure it can be used in future writes
            self.free_pages.add(physical_addr)
            # Since this block now has at least one free page, add it to free_blocks
            self.free_blocks.add(block_id)
            
        return success

    def get_block_and_page_ids(self, physical_addr: int) -> Tuple[int, int]:
        ##
        # @brief Convert physical address to block and page IDs
        #
        # @param physical_addr Physical address to convert
        # @return Tuple[int, int] Block ID and page ID
        ##
        return (physical_addr // config.PAGES_PER_BLOCK,
                physical_addr % config.PAGES_PER_BLOCK)

    def sync_block_wear_level(self, block_id: int):
        ##
        # @brief Update tracked wear level for a block
        #
        # @param block_id Block ID to update
        ##
        status = self.flash_memory.get_block_status(block_id)
        self.block_wear_levels[block_id] = status['erase_count']

    def read(self, logical_addr: int) -> Optional[bytes]:
        ##
        # @brief Read data from flash memory.
        #
        # @param logical_addr Logical address to read from
        # @return Optional[bytes] Data read from memory, or None if address not mapped
        ##
        self.validate_logical_address(logical_addr)
        physical_addr = self.logical_to_physical[logical_addr]
        block_id, page_id = self.get_block_and_page_ids(physical_addr)
        
        return self.flash_memory.read(block_id, page_id)

    def relocate_programmed_pages(self, block_addr: int) -> bool:
        ##
        # @brief Move all valid (PROGRAMMED) pages from a block to free pages elsewhere.
        #
        # @param block_addr Block to relocate data from
        # @return bool True if all valid pages were successfully relocated
        ##
        # Calculate page range
        start_page = block_addr * config.PAGES_PER_BLOCK
        end_page = start_page + config.PAGES_PER_BLOCK
        
        # Find all valid pages and their corresponding logical addresses
        valid_pages = []
        for page_offset in range(config.PAGES_PER_BLOCK):
            physical_addr = start_page + page_offset
            block_id, page_id = self.get_block_and_page_ids(physical_addr)
            page = self.flash_memory.blocks[block_id].pages[page_id]
            
            if page.state == PageState.PROGRAMMED:
                # Find logical address that maps to this physical address
                logical_addr = self.find_logical_address(block_id, page_id)
                        
                if logical_addr is not None:
                    # Store the logical address and its data for relocation
                    data = self.flash_memory.read(block_id, page_id)
                    valid_pages.append((logical_addr, data))
                
        # Relocate each valid page
        for logical_addr, data in valid_pages:
            # Get a new free page
            new_physical = self.get_next_free_page()
            if new_physical is None:
                return False  # No free pages available
                
            # Write data to new location
            if not self.write_to_physical(new_physical, data):
                return False  # Write failed
                
            # Update mapping
            self.logical_to_physical[logical_addr] = new_physical
            
        return True  # All valid pages successfully relocated

    def erase_block(self, block_addr: int) -> bool:
        ##
        # @brief Erase a block, relocating any valid data as needed.
        #
        # @param block_addr Block address to erase
        # @return bool True if block was successfully erased
        # @throws FTLAddressError If logical addresses remain mapped to this block after erasure
        ##
        # Calculate page range for this block
        start_page = block_addr * config.PAGES_PER_BLOCK
        end_page = start_page + config.PAGES_PER_BLOCK  
        
        # Check if block has any valid pages
        has_valid_pages = False
        for page_offset in range(config.PAGES_PER_BLOCK):
            block_id, page_id = block_addr, page_offset
            page = self.flash_memory.blocks[block_id].pages[page_id]
            if page.state == PageState.PROGRAMMED:
                has_valid_pages = True
                break
                
        # If block has valid pages, try to relocate them
        if has_valid_pages:
            if not self.relocate_programmed_pages(block_addr):
                print(f"Could not relocate valid pages from block {block_addr}")
                return False
        
        # Safety check: Verify no logical addresses are mapped to this block
        mapped_addresses = []
        for logical, physical in enumerate(self.logical_to_physical):
            if start_page <= physical < end_page:
                mapped_addresses.append(logical)
                
        if mapped_addresses:
            print(f"Error: Logical addresses {mapped_addresses} still mapped to block {block_addr} before erase")
            return False
        
        # Erase the block
        if not self.flash_memory.erase_block(block_addr):
            print(f"Hardware erase operation failed for block {block_addr}")
            return False
            
        # Add all pages in block back to free list
        new_free_pages = set(range(start_page, end_page))
        self.free_pages.update(new_free_pages)
        self.free_blocks.add(block_addr)
        
        # Final safety check: Double check no logical addresses are mapped to this newly erased block
        post_erase_mapped = []
        for logical, physical in enumerate(self.logical_to_physical):
            if start_page <= physical < end_page:
                post_erase_mapped.append(logical)
                
        if post_erase_mapped:
            # This should never happen if prior checks passed
            error_msg = f"CRITICAL ERROR: Logical addresses {post_erase_mapped} still mapped to block {block_addr} after erase"
            print(error_msg)
            raise FTLAddressError(error_msg)
        
        # Update wear level for the erased block
        self.sync_block_wear_level(block_addr)
        
        return True

    def find_logical_address(self, block_id: int, page_id: int) -> Optional[int]:
        ##
        # @brief Find the logical address mapped to a specific physical address.
        #
        # @param block_id Block ID of the physical address
        # @param page_id Page ID within the block
        # @return Optional[int] Logical address if mapping exists, None otherwise
        ##
        physical_addr = block_id * config.PAGES_PER_BLOCK + page_id
        
        # Search the mapping table for this physical address
        try:
            return self.logical_to_physical.index(physical_addr)
        except ValueError:
            return None

    def find_blocks_for_garbage_collection(self) -> List[int]:
        ##
        # @brief Find all blocks suitable for garbage collection.
        # A block is considered suitable when either:
        # 1. It has invalid pages but no programmed or erased pages
        # 2. (invalid_pages / (programmed_pages + erased_pages)) > GC_THRESHOLD
        #
        # @return List[int] Block IDs that meet the garbage collection criteria
        ##
        gc_candidates = []
        
        # Iterate through all physical blocks to find GC candidates
        for block_id in range(config.PHYSICAL_BLOCKS):
              
            # Get detailed block status information
            status = self.flash_memory.get_block_status(block_id)
            invalid_pages = status['invalid_pages']
            programmed_pages = status['programmed_pages']
            erased_pages = status['erased_pages']
            
            # CASE 1: Block has invalid pages but no valid content
            # This is a prime candidate for garbage collection because erasing it
            # won't require any data relocation
            if invalid_pages > 0 and (programmed_pages + erased_pages) == 0:
                gc_candidates.append(block_id)
                continue
                
            # CASE 2: Block has some valid content but meets the GC threshold
            # GC_THRESHOLD determines when the benefit of reclaiming invalid pages
            # outweighs the cost of relocating valid pages
            if (programmed_pages + erased_pages) > 0:
                # Calculate ratio of "garbage" (invalid pages) to valid content
                gc_ratio = invalid_pages / (programmed_pages + erased_pages)
                
                # If this block exceeds our threshold ratio, add it as a candidate
                if gc_ratio > config.GC_THRESHOLD:
                    gc_candidates.append(block_id)
        
        return gc_candidates

    def garbage_collect(self) -> bool:
        ##
        # @brief Perform garbage collection to reclaim space.
        # Finds all blocks that meet the garbage collection criteria and erases them.
        #
        # The garbage collection process consists of:
        # 1. Identifying candidate blocks based on invalid/valid page ratios
        # 2. For each candidate block:
        #    - Relocating any programmed (valid) pages
        #    - Erasing the block to reclaim space
        #    - Updating free page and block tracking
        #
        # @return bool True if garbage collection freed some space
        ##
        # Step 1: Identify candidate blocks for garbage collection
        target_blocks = self.find_blocks_for_garbage_collection()
        if not target_blocks:
            # No blocks qualified for garbage collection
            return False
        
        space_freed = False
        
        # Step 2: Process each candidate block
        for block_id in target_blocks:
            try:
                # Use our existing erase_block method which handles:
                # - Relocation of programmed pages to preserve data
                # - Mapping updates to maintain logical-to-physical references
                # - Block erasure at the physical layer
                # - Free page tracking updates
                if self.erase_block(block_id):
                    space_freed = True
                    # Note: We don't need to update wear levels here as
                    # erase_block already handles this via sync_block_wear_level
            except FTLAddressError as e:
                # If erase fails due to address errors, log and continue with other blocks
                # This provides resilience - if one block fails, we still try others
                print(f"Error during garbage collection of block {block_id}: {e}")
                continue
                
        # Return true if we successfully freed any space
        return space_freed
