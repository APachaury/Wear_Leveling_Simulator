## @file wear_leveling.py
## @brief Implementation of static wear leveling algorithm.
## @details This module implements a static wear leveling strategy that periodically moves cold data
## from less worn pages to more worn pages.

# Required imports for type hints and numerical operations
from typing import List, Tuple, Optional, TYPE_CHECKING
import numpy as np
import config
from flash_memory import FlashMemory, PageState, FlashAddressError
import statistics

if TYPE_CHECKING:
    from ftl import FlashTranslationLayer, FTLAddressError

# Quite unsure about how the circular dependency with FTL works, it may or may not be correct

class WearLevelingError(Exception):
    ##
    # @brief Exception raised for wear leveling errors.
    ##
    pass

class WearLeveling:
    ##
    # @brief Implements static wear leveling
    ##
    
    def __init__(self, flash_memory: FlashMemory, ftl: 'FlashTranslationLayer') -> None:
        ##
        # @brief Initialize wear leveling with references to flash_memory and FTL.
        #
        # @param flash_memory Flash memory instance to perform wear leveling on
        # @param ftl FTL instance to handle address mapping
        ##
        self.flash_memory = flash_memory
        self.ftl = ftl
        self.last_leveling_operation = 0  # Track operations-based wear leveling
        self.last_leveling_time = 0  # Track time-based wear leveling
        
    def set_ftl(self, ftl: 'FlashTranslationLayer') -> None:
        ##
        # @brief Set the FTL reference after FTL initialization
        #
        # @param ftl FTL instance to handle address mapping
        ##
        self.ftl = ftl

    def should_trigger_static_wear_leveling(self, operation_count: int) -> bool:
        ##
        # @brief Determine if static wear leveling should be triggered based on operation count.
        #
        # @param operation_count Current operation count
        # @return bool True if static wear leveling should be triggered
        ##
        # Check if we've done enough operations since last wear leveling
        operations_since_last = operation_count - self.last_leveling_operation
        if operations_since_last < config.STATIC_WEAR_LEVEL_CHECK_INTERVAL:
            return False
            
        # Check if any blocks were recently active based on operations
        # Maybe we should change this such that we look at whether a FRACTION of blocks were recently active
        # instead of any 1 block. This will probably always return True
        for block in self.flash_memory.blocks:
            if block.was_recently_active(operation_count):
                return True
                
        return False
        
    def return_static_wear_leveling_candidates(self) -> List[Tuple[int, int]]:
        ##
        # @brief Find candidate pairs of blocks for static wear leveling.
        #
        # Selection criteria:
        # 1. Significant difference in wear between high and low wear blocks
        # 2. High wear blocks must be recently active ("hot")
        # 3. Low wear blocks must be completely empty
        # 4. Only consider blocks above/below median wear to reduce iteration count
        #
        # @return List[Tuple[int, int]] List of (high_wear_block, low_wear_block) pairs
        ##
        # Use PE_CYCLE_DIFFERENCE_THRESHOLD from config to determine what's a significant difference
        WEAR_DIFFERENCE_THRESHOLD = config.PE_CYCLE_DIFFERENCE_THRESHOLD
        current_operation_count = self.flash_memory.operation_count
        
        # Get all blocks with their IDs and sort by PE cycles
        all_blocks = [(block_id, block.get_pe_cycles()) 
                     for block_id, block in enumerate(self.flash_memory.blocks)]
        
        # Sort all blocks by PE cycles (lowest to highest)
        all_blocks.sort(key=lambda x: x[1])
        
        # Find the median index (we'll only loop through blocks above/below this)
        median_index = len(all_blocks) // 2
        
        # Find "hot" blocks with high PE cycles (only look at upper half of blocks)
        high_wear_blocks = []
        for block_id, pe_cycles in all_blocks[median_index:]:  # Only loop through upper half!
            block = self.flash_memory.blocks[block_id]
            # Only consider blocks that are "hot" (recently active) and have valid data
            if (self.is_the_block_hot(block_id, current_operation_count) and 
                any(page.state == PageState.PROGRAMMED for page in block.pages)):
                high_wear_blocks.append((block_id, pe_cycles))
        
        # Sort high wear blocks by PE cycles (highest first)
        high_wear_blocks.sort(key=lambda x: x[1], reverse=True)
        
        # Find completely empty blocks with low PE cycles (only look at lower half of blocks)
        low_wear_blocks = []
        for block_id, pe_cycles in all_blocks[:median_index]:  # Only loop through lower half!
            # Only consider completely empty blocks
            if self.is_block_completely_empty(block_id):
                low_wear_blocks.append((block_id, pe_cycles))
        
        # Sort low wear blocks by PE cycles (lowest first)
        low_wear_blocks.sort(key=lambda x: x[1])
        
        # Create pairs with significant wear difference
        # Match highest wear with lowest wear, second highest with second lowest, etc.
        candidates = []
        
        # Determine how many pairs we can create (minimum of high wear and low wear blocks lengths)
        num_pairs = min(len(high_wear_blocks), len(low_wear_blocks))
        
        # Pair blocks in corresponding positions (highest with lowest, etc.)
        for i in range(num_pairs):
            high_block_id, high_pe = high_wear_blocks[i]
            low_block_id, low_pe = low_wear_blocks[i]
            
            # Don't pair a block with itself
            if high_block_id == low_block_id:
                continue
                
            # Check if the wear difference is significant
            wear_diff = high_pe - low_pe
            if wear_diff >= WEAR_DIFFERENCE_THRESHOLD:
                candidates.append((high_block_id, low_block_id))
        
        return candidates
    
    def is_the_block_hot(self, block_id: int, current_operation_count: int) -> bool:
        ##
        # @brief Determine if a block is "hot" (recently active).
        #
        # A block is considered hot if it has been active within the 
        # ACTIVITY_WINDOW threshold of operations.
        #
        # @param block_id Block ID to check
        # @param current_operation_count Current operation count
        # @return bool True if the block is hot (recently active)
        ##
        block = self.flash_memory.blocks[block_id]
        
        # Get the most recent operation time on this block
        last_operation = block.last_modified_time
        
        # If the block has never been used, it's not hot
        if last_operation == 0:
            return False
            
        # Check if the block was active within the threshold window
        operations_since_last_activity = current_operation_count - last_operation
        return operations_since_last_activity <= config.ACTIVITY_WINDOW

    def perform_static_wear_leveling(self, operation_count: int) -> bool:
        ##
        # @brief Perform static wear leveling by moving data from high-wear to low-wear blocks.
        #
        # This method:
        # 1. Gets candidate pairs of blocks for wear leveling
        # 2. For each pair, moves data from high-wear to low-wear block 
        # 3. Updates the FTL mapping accordingly
        #
        # @param operation_count Current operation count
        # @return bool True if wear leveling was performed for at least one pair
        ##
        # Get candidate pairs for wear leveling
        candidate_pairs = self.return_static_wear_leveling_candidates()
        
        if not candidate_pairs:
            return False
            
        # Track if we performed wear leveling for at least one pair
        wear_leveling_performed = False
        
        # Process each candidate pair
        for high_wear_block, low_wear_block in candidate_pairs:
            # Verify that the low_wear_block is completely empty
            if not self.is_block_completely_empty(low_wear_block):
                continue
                
            # Move contents from high_wear_block to low_wear_block
            if self.move_block_contents(high_wear_block, low_wear_block):
                wear_leveling_performed = True
                print(f"Performed static wear leveling: moved data from block {high_wear_block} to block {low_wear_block}")

        # Update the last leveling operation count if we performed any wear leveling
        if wear_leveling_performed:
            self.last_leveling_operation = operation_count
            
        return wear_leveling_performed
    
    def is_block_completely_empty(self, block_id: int) -> bool:
        ##
        # @brief Check if a block is completely empty (all pages in ERASED state).
        #
        # @param block_id Block ID to check
        # @return bool True if all pages in the block are in ERASED state
        ##
        block = self.flash_memory.blocks[block_id]
        return all(page.state == PageState.ERASED for page in block.pages)
    
    def move_block_contents(self, source_block: int, target_block: int) -> bool:
        ##
        # @brief Move all valid data from source block to target block.
        #
        # @param source_block Block ID to move data from
        # @param target_block Block ID to move data to
        # @return bool True if any data was successfully moved
        # @throws WearLevelingError If an error occurs during the move operation
        ##
        # Verify target block is completely empty
        if not self.is_block_completely_empty(target_block):
            return False
            
        moved_any_data = False
        source_block_obj = self.flash_memory.blocks[source_block]
        
        # For each page in the source block
        for source_page_id, source_page in enumerate(source_block_obj.pages):
            # Skip pages that don't have valid data
            if source_page.state != PageState.PROGRAMMED:
                continue
                
            # Find the logical address for this physical page
            source_logical_addr = self.ftl.find_logical_address(source_block, source_page_id)
            if source_logical_addr is None:
                # This should never happen - if a page is PROGRAMMED, it must have a logical address
                raise WearLevelingError(f"Inconsistent state detected: Page {source_page_id} in block {source_block} is PROGRAMMED but has no logical address mapping")
                
            # Calculate target page ID and address
            target_page_id = source_page_id  # Use same position in target block
            target_physical_addr = target_block * config.PAGES_PER_BLOCK + target_page_id
            
            try:
                # Read data from source
                source_physical_addr = source_block * config.PAGES_PER_BLOCK + source_page_id
                data = self.flash_memory.read(source_physical_addr)
                
                # Write data to target
                self.flash_memory.write(target_physical_addr, data)
                
                # Update FTL mapping to point to new location
                self.ftl.logical_to_physical[source_logical_addr] = target_physical_addr
                
                # Invalidate old page
                self.ftl.invalidate_page(source_block, source_page_id)
                
                moved_any_data = True
            except Exception as e:
                # If there was an error, propagate it
                raise WearLevelingError(f"Error moving data from block {source_block} to {target_block}: {str(e)}") from e
        
        return moved_any_data
