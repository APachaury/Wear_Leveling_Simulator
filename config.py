## @file
## @brief Configuration parameters for the flash memory simulation.
## @details This module contains all the constant values and thresholds used
## throughout the simulation. These values can be adjusted to experiment with
## different memory configurations and behaviors.

# MEMORY ARCHITECTURE #
PAGE_SIZE = 2048
LOGICAL_BLOCKS = 1024
PHYSICAL_BLOCKS = 1096
PAGES_PER_BLOCK = 64
LOGICAL_PAGES = LOGICAL_BLOCKS * PAGES_PER_BLOCK # Total pages visible to user
PHYSICAL_PAGES = PHYSICAL_BLOCKS * PAGES_PER_BLOCK # Total physical pages including over-provisioning
TOTAL_MEMORY_SIZE = PAGE_SIZE * PHYSICAL_PAGES # (2KB * 64 * 1096)

# ENDURANCE SETTINGS #
MAX_PE_CYCLES = 10000

# GARBAGE COLLECTION (GC) #
GC_THRESHOLD = 0.7

# NOTE: Future enhancement option
# Whether to run garbage collection in background during idle times
# If False, GC only runs when absolutely necessary
# BACKGROUND_GC = True

# WEAR LEVELING #
PE_CYCLE_DIFFERENCE_THRESHOLD = 200 # P/E cycle difference to trigger wear leveling
STATIC_WEAR_LEVEL_CHECK_INTERVAL = 1000 # Check wear leveling every 1000 operations
DYNAMIC_WEAR_WINDOW = 100 # Maximum wear difference allowed when selecting free blocks for dynamic wear leveling
ACTIVITY_WINDOW = 1000 # Window to consider a block "recently active" in terms of number of operations

# SIMULATION PARAMETERS #
IDLE_PROBABILITY = 0.3 # 30% of operations are idle
WRITE_WEIGHT = 40 # Weight for write operations
READ_WEIGHT = 40 # Weight for read operations
ERASE_WEIGHT = 20 # Weight for erase operations
SIMULATION_TIME_UNITS = 10 # Total time units to simulate (each unit is exactly one operation)
SIMULATION_END_THRESHOLD = 0.2 # Stop when 20% of pages are dead
