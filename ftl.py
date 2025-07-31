## @file ftl.py
## @brief Flash Translation Layer (FTL) implementation.
## @details This module implements the Flash Translation Layer, which manages the mapping between
## logical addresses (used by the host) and physical addresses (actual flash memory locations).
## The FTL also handles both static and dynamic wear leveling, and garbage collection

from typing import Dict, Optional, List, Set, Tuple
import config
from flash_memory import FlashMemory, FlashAddressError
from wear_leveling import WearLeveling
from enum import Enum

class PageState(Enum):
    ##
    # @brief Enumerates the possible states of a page.
    ##
    ERASED = 0
    PROGRAMMED = 1
    INVALID = 2
    DEAD = 3

class FTLAddressError(Exception):
    """Exception raised for invalid logical or physical addresses."""
    pass

class FTLMappingError(Exception):
    """Exception raised for logical-to-physical mapping inconsistencies."""
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
        
        # Initialize logical to physical mapping: one-to-one for first LOGICAL_PAGES, remaining physical pages unmapped (-1)
        self.logical_to_physical = [-1] * config.PHYSICAL_PAGES
        for i in range(config.LOGICAL_PAGES):
            self.logical_to_physical[i] = i

        self.free_pages = set(range(config.PHYSICAL_PAGES))
        self.free_blocks = set(range(config.PHYSICAL_BLOCKS))
        self.block_erase_count = [0] * config.PHYSICAL_BLOCKS
        self.written_pages = set() # Track all pages written to for wear analysis
    
    def read(self, logical_addr: int) -> Optional[bytes]:
        ##
        # @brief Read data from flash memory.
        #
        # @param logical_addr Logical address to read from
        # @return Optional[bytes] Data read from memory, or None if address not mapped
        ##
        self.validate_logical_address(logical_addr)
        physical_addr = self.logical_to_physical[logical_addr]
        
        # Check if address is unmapped
        if physical_addr == -1:
            return None  # Address not mapped to any physical location
        
        # Validate physical address before conversion
        self.validate_physical_address(physical_addr)
        
        block_id, page_id = self.get_block_and_page_ids(physical_addr)
        return self.flash_memory.read(block_id, page_id)
        
    def erase(self, block_id: int) -> bool:
        """
        Erase a block by its block ID. This will relocate any valid data and then erase the block.
        
        @param block_id Block ID to erase
        @return bool True if block was successfully erased
        """
        # Erase the entire block using erase_block
        success = self.erase_block(block_id)
        if not success:
            print(f"Error: Failed to erase block {block_id}")
            exit(1)
        if success:
            print(f"Erased block {block_id}")
        return success
    
    def write(self, logical_addr: int, data: bytes) -> bool:
        ##
        # @brief Main entry point for writes
        #
        # @param logical_addr Logical address to write to
        # @param data Data to write
        # @return bool True if write succeeded
        ##
        if self.wear_leveling_enabled:
            return self.write_with_dynamic_wear_leveling(logical_addr, data)
        else:
            return self.write_without_wear_leveling(logical_addr, data)

    def write_without_wear_leveling(self, logical_addr: int, data: bytes) -> bool:
        ##
        # @brief Write without any wear leveling
        #
        # @param logical_addr Logical address to write to
        # @param data Data to write
        # @return bool True if write succeeded
        ##
        self.validate_logical_address(logical_addr)

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
            self.logical_to_physical[logical_addr] = physical_addr # Update mapping
            self.verify_mapping()  # Verify mapping integrity
            print(f"[No WL] Op={self.flash_memory.operation_count} Wrote data to physical address {physical_addr}")
            return True
            
        return False
    
    def write_with_dynamic_wear_leveling(self, logical_addr: int, data: bytes) -> bool:
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
            self.verify_mapping()  # Verify mapping integrity
            # Update wear tracking after write
            block_id = physical_addr // config.PAGES_PER_BLOCK
            self.sync_block_wear_level(block_id)
            print(f"[Dynamic WL] Op={self.flash_memory.operation_count} Wrote data to physical address {physical_addr}")
            return True
            
        return False

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
        
        # Get block and page info before write
        block_id = physical_addr // config.PAGES_PER_BLOCK
        page_id = physical_addr % config.PAGES_PER_BLOCK
        block = self.flash_memory.blocks[block_id]
        page = block.pages[page_id]
        current_pe = page.pe_cycles

        # Attempt to write data to flash memory hardware
        success = self.flash_memory.write(block_id, page_id, data)
        
        if success:
            # Write succeeded - ensure page is not in free_pages as it's now PROGRAMMED
            self.free_pages.discard(physical_addr)
            # Update block status as it may no longer have free pages
            self.update_block_free_status(block_id)
            self.written_pages.add(physical_addr)
            
        else:
            # Write failed - page remains in ERASED state and is still usable
            # Add it back to free_pages to ensure it can be used in future writes
            self.free_pages.add(physical_addr)
            # Since this block now has at least one free page, add it to free_blocks
            self.free_blocks.add(block_id)
            
        return success
    
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
        min_wear = min(self.block_erase_count[block_id] for block_id in self.free_blocks)
        candidates = {
            block_id for block_id in self.free_blocks
            if self.block_erase_count[block_id] <= min_wear + config.DYNAMIC_WEAR_WINDOW
        }

        # Get first free page from candidate blocks
        for page in self.free_pages:
            if page // config.PAGES_PER_BLOCK in candidates:
                self.free_pages.discard(page)
                # Unmap any logical addresses that were mapped to this physical page
                for logical_addr, mapped_physical in enumerate(self.logical_to_physical):
                    if mapped_physical == page:
                        self.logical_to_physical[logical_addr] = -1
                return page

        return None

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
        print("Garbage Collecting...")
        target_blocks = self.find_blocks_for_garbage_collection()
        if not target_blocks:
            # No blocks qualified for garbage collection
            print("No blocks qualified for garbage collection")
            return False
        
        space_freed = False
        
        # Step 2: Process each candidate block
        for block_id in target_blocks:
            try:
                if self.erase_block(block_id):
                    space_freed = True
                else: 
                    print(f"Error: Failed to erase block {block_id}")
                    exit(1)
            except FTLAddressError as e:
                print(f"Error during garbage collection of block {block_id}: {e}")
                continue
        
        print(f"Garbage collection freed {space_freed} pages")
        # Return true if we successfully freed any space
        return space_freed
    
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
            dead_pages = status['dead_pages']
            
            # Print block status
            print(f"Block {block_id} status:")
            print(f"  Invalid: {invalid_pages}, Programmed: {programmed_pages}, Erased: {erased_pages}, Dead: {dead_pages}")
            
            # CASE 1: Block has invalid pages but no valid content
            # This is a prime candidate for garbage collection because erasing it
            # won't require any data relocation
            if invalid_pages > 0 and programmed_pages == 0:
                print(f"  -> Selected for GC (Case 1: Has invalid pages but no valid content)")
                gc_candidates.append(block_id)
                continue
                
            # CASE 2: Block has some valid content but meets the GC threshold
            # GC_THRESHOLD determines when the benefit of reclaiming invalid pages outweighs the cost of relocating valid pages
            gc_ratio = invalid_pages / (programmed_pages + erased_pages) if (programmed_pages + erased_pages) > 0 else 0
            print(f"  -> GC ratio: {gc_ratio:.2f} (threshold: {config.GC_THRESHOLD})")
            
            if gc_ratio > config.GC_THRESHOLD:
                print(f"  -> Selected for GC (Case 2: Meets GC threshold)")
                gc_candidates.append(block_id)
        
        print(f"Found {len(gc_candidates)} blocks for garbage collection")
        return gc_candidates
    
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
        
        # Check if block has any programmed pages
        has_programmed_pages = False
        for page_offset in range(config.PAGES_PER_BLOCK):
            block_id, page_id = block_addr, page_offset
            page = self.flash_memory.blocks[block_id].pages[page_id]
            if page.state == PageState.PROGRAMMED:
                has_programmed_pages = True
                break
                
        # If block has programmed pages, try to relocate them
        if not self.relocate_programmed_pages(block_addr):
            print(f"Could not relocate valid pages from block {block_addr}")
            return False
        
        # Safety check: Verify no logical addresses are mapped to this block
        mapped_addresses = []
        for logical, physical in enumerate(self.logical_to_physical):
            if start_page <= physical < end_page:
                mapped_addresses.append(logical)
                
        if mapped_addresses:
            # This should never happen since relocate_programmed_pages should have handled all valid pages
            error_msg = f"Logical addresses {mapped_addresses} still mapped to block {block_addr} after relocation"
            print(error_msg)
            raise FTLAddressError(error_msg)
        
        # Erase the block
        if not self.flash_memory.erase_block(block_addr):
            print(f"Error: Hardware erase operation failed for block {block_addr}")
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
        self.verify_mapping()
        
        return True

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
        programmed_pages = []
        block_id = block_addr
        
        # First pass: Find all logical addresses that map to this block
        mapped_logicals = []
        for logical_addr, physical_addr in enumerate(self.logical_to_physical):
            if start_page <= physical_addr < end_page:
                mapped_logicals.append(logical_addr)
                
        # Second pass: For each mapped logical address, get data if page is programmed
        for logical_addr in mapped_logicals:
            physical_addr = self.logical_to_physical[logical_addr]
            _, page_id = self.get_block_and_page_ids(physical_addr)
            page = self.flash_memory.blocks[block_id].pages[page_id]
            
            if page.state == PageState.PROGRAMMED:
                # Store the logical address and its data for relocation
                data = self.flash_memory.read(block_id, page_id)
                programmed_pages.append((logical_addr, data))
            else:
                # Page is mapped but not programmed, just unmap it
                # print(f"Unmapping non-programmed logical {logical_addr} from physical {physical_addr}")
                self.logical_to_physical[logical_addr] = -1
                
        # Relocate each programmed page
        for logical_addr, data in programmed_pages:
            # Get a new free page
            new_physical = self.get_next_free_page()
            if new_physical is None:
                print("Error: No free pages available")
                exit(1)
                
            # Write data to new location
            if not self.write_to_physical(new_physical, data):
                print("Error: Write failed")
                exit(1)
                
            # Set old physical address to -1 and update mapping to new location
            old_physical = self.logical_to_physical[logical_addr]
            self.logical_to_physical[logical_addr] = -1  # First set to unmapped
            self.logical_to_physical[logical_addr] = new_physical  # Then set to new location
            print(f"Relocated logical address {logical_addr} from physical address {old_physical} to {new_physical}")
            self.verify_mapping()  # Verify mapping integrity
            
        return True  # All valid pages successfully relocated
    
    def get_next_free_page(self) -> Optional[int]:
        ##
        # @brief Get next free page without wear leveling
        #
        # Before returning a free page, unmap any logical addresses that were previously
        # mapped to this physical page to maintain mapping consistency.
        #
        # @return Optional[int] Physical page address if available, None if no free pages
        ##
        if not self.free_pages:
            return None
            
        page = min(self.free_pages)  # Get first available page
        self.free_pages.discard(page)
        
        # Before returning the page, unmap any logical addresses that point to it
        for logical_addr, mapped_physical in enumerate(self.logical_to_physical):
            if mapped_physical == page:
                print(f"Unmapping logical {logical_addr} from physical {page} before reuse")
                self.logical_to_physical[logical_addr] = -1
                
        return page
    
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

    def verify_mapping(self) -> None:
        ##
        # @brief Verify mapping integrity based on current state.
        #
        # Initial state: One-to-one mapping where logical_addr maps to same physical_addr
        # After writes: Ensure no physical address is mapped by multiple logical addresses
        #
        # @throws FTLMappingError If mapping integrity is violated
        ##
    
        # Verify no physical address has multiple logical addresses
        # Skip unmapped addresses (-1) since multiple logical addresses can be unmapped
        for logical_addr, physical_addr in enumerate(self.logical_to_physical):
            if physical_addr == -1:  # Skip unmapped addresses
                continue
            count = self.logical_to_physical.count(physical_addr)
            if count > 1:
                # Find all logical addresses that map to this physical address
                conflicting_logicals = [i for i, p in enumerate(self.logical_to_physical) if p == physical_addr]
                print("\n=== MAPPING ERROR DETECTED ===")
                print("\nConflicting mappings:")
                print("-" * 30)
                for logical in conflicting_logicals:
                    print(f"Logical {logical} -> Physical {self.logical_to_physical[logical]}")
                print("-" * 30)
                raise FTLMappingError(
                    f"Physical address {physical_addr} is mapped by multiple logical addresses: {conflicting_logicals}"
                )
        
        # Verify all PROGRAMMED pages have a logical mapping
        for block_id in range(config.PHYSICAL_BLOCKS):
            for page_id in range(config.PAGES_PER_BLOCK):
                if self.flash_memory.blocks[block_id].pages[page_id].state == PageState.PROGRAMMED:
                    physical_addr = block_id * config.PAGES_PER_BLOCK + page_id
                    has_mapping = False
                    for logical_addr, mapped_physical in enumerate(self.logical_to_physical):
                        if mapped_physical == physical_addr:
                            has_mapping = True
                            break
                    if not has_mapping:
                        print(f"\n=== MAPPING ERROR DETECTED ===")
                        print(f"PROGRAMMED page at physical address {physical_addr} (block {block_id}, page {page_id}) has no logical mapping")
                        print(f"Invalidating inconsistent page")
                        self.flash_memory.invalidate_page(block_id, page_id)
    
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
        self.block_erase_count[block_id] = status['erase_count']
    
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
        block_id, page_id = self.get_block_and_page_ids(physical_addr)
        
        # Find any logical address that maps to this physical address and set it to -1
        for logical_addr, mapped_physical in enumerate(self.logical_to_physical):
            if mapped_physical == physical_addr:
                self.logical_to_physical[logical_addr] = -1
                print(f"Unmapped logical address {logical_addr} from invalidated physical address {physical_addr}")
        
        self.flash_memory.invalidate_page(block_id, page_id)
        self.free_pages.discard(physical_addr)
        
        # Update free blocks status
        self.update_block_free_status(block_id)

    def get_block_and_page_ids(self, physical_addr: int) -> Tuple[int, int]:
        ##
        # @brief Convert physical address to block and page IDs
        #
        # @param physical_addr Physical address to convert
        # @return Tuple[int, int] Block ID and page ID
        ##
        return (physical_addr // config.PAGES_PER_BLOCK,
                physical_addr % config.PAGES_PER_BLOCK)

    def find_logical_address(self, block_id: int, page_id: int) -> Optional[int]:
        ##
        # @brief Find the logical address mapped to a specific physical address.
        #
        # @param block_id Block ID of the physical address
        # @param page_id Page ID within the block
        # @return Optional[int] Logical address if mapping exists, None otherwise
        ##
        physical_addr = block_id * config.PAGES_PER_BLOCK + page_id
        
        # Search through the mapping table for this physical address
        # The index in logical_to_physical is the logical address
        for logical_addr, mapped_physical in enumerate(self.logical_to_physical):
            if mapped_physical == physical_addr:
                return logical_addr
        return None
