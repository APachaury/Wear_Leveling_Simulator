## @file
## @brief Configuration parameters for the flash memory simulation.
## @details This module contains all the constant values and thresholds used
## throughout the simulation. These values can be adjusted to experiment with
## different memory configurations and behaviors.

# MEMORY ARCHITECTURE #

## @defgroup memory_architecture Memory Architecture
## @{
## @brief Basic unit of storage in flash memory (2KB in bytes - typical size for NAND flash memory)
PAGE_SIZE = 2048  # 2KB in bytes - typical size for NAND flash memory

## @brief Number of blocks visible to user
LOGICAL_BLOCKS = 1024   # Number of blocks visible to user
## @brief Total blocks including over-provisioning (72 extra blocks)
PHYSICAL_BLOCKS = 1096  # Total blocks including over-provisioning (72 extra blocks)
## @brief Number of pages in each block
PAGES_PER_BLOCK = 64    # Number of pages in each block

# Derived Configuration
## @brief Total pages visible to user
LOGICAL_PAGES = LOGICAL_BLOCKS * PAGES_PER_BLOCK    # Total pages visible to user
## @brief Total physical pages including over-provisioning
PHYSICAL_PAGES = PHYSICAL_BLOCKS * PAGES_PER_BLOCK  # Total physical pages including over-provisioning

## @brief Total memory size in bytes (2KB * 64 * 1096)
TOTAL_MEMORY_SIZE = PAGE_SIZE * PHYSICAL_PAGES      # (2KB * 64 * 1096)
## @}

# ENDURANCE SETTINGS #

## @defgroup endurance_settings Endurance Settings
## @{
## @brief Maximum number of Program/Erase cycles a page can endure (10K cycles is typical for SLC NAND flash)
MAX_PE_CYCLES = 10000  # 10K cycles is typical for SLC NAND flash
## @}

# GARBAGE COLLECTION (GC) #

## @defgroup garbage_collection Garbage Collection
## @{
## @brief Threshold ratio of invalid pages that triggers garbage collection
GC_THRESHOLD = 0.7  # Ratio of invalid pages to trigger garbage collection

# NOTE: Future enhancement option
# Whether to run garbage collection in background during idle times
# If False, GC only runs when absolutely necessary
# BACKGROUND_GC = True
## @}

# WEAR LEVELING #

## @defgroup wear_leveling Wear Leveling
## @{
## @brief P/E cycle difference to trigger wear leveling
PE_CYCLE_DIFFERENCE_THRESHOLD = 200   # P/E cycle difference to trigger wear leveling
## @brief Check wear leveling every 1000 operations
STATIC_WEAR_LEVEL_CHECK_INTERVAL = 1000  # Check wear leveling every 1000 operations
## @brief Maximum wear difference allowed when selecting free blocks for dynamic wear leveling
DYNAMIC_WEAR_WINDOW = 100   # Maximum wear difference allowed when selecting free blocks for dynamic wear leveling

## @brief Window to consider a block "recently active" in terms of number of operations
ACTIVITY_WINDOW = 1000  # Window to consider a block "recently active" in terms of number of operations
## @}

# SIMULATION PARAMETERS #

## @defgroup simulation_parameters Simulation Parameters
## @{
## @brief Probability of idle operations (30% of operations are idle)
IDLE_PROBABILITY = 0.3  # 30% of operations are idle
## @brief Weight for write operations
WRITE_WEIGHT = 40       # Weight for write operations
## @brief Weight for read operations
READ_WEIGHT = 40        # Weight for read operations
## @brief Weight for erase operations
ERASE_WEIGHT = 20       # Weight for erase operations
## @brief Total time units to simulate (each unit is exactly one operation)
SIMULATION_TIME_UNITS = 10  # Total time units to simulate (each unit is exactly one operation)

## @brief Stop when 20% of pages are dead
SIMULATION_END_THRESHOLD = 0.2  # Stop when 20% of pages are dead
## @}
