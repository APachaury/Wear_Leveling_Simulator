## @file
## @brief Configuration parameters for the flash memory simulation.
## @details This module contains all the constant values and thresholds used
## throughout the simulation. These values can be adjusted to experiment with
## different memory configurations and behaviors.

# MEMORY ARCHITECTURE #
PAGE_SIZE = 16
LOGICAL_BLOCKS = 128
PHYSICAL_BLOCKS = 160
PAGES_PER_BLOCK = 16
LOGICAL_PAGES = LOGICAL_BLOCKS * PAGES_PER_BLOCK # Total pages visible to user
PHYSICAL_PAGES = PHYSICAL_BLOCKS * PAGES_PER_BLOCK # Total physical pages including over-provisioning
TOTAL_MEMORY_SIZE = PAGE_SIZE * PHYSICAL_PAGES

# ENDURANCE SETTINGS #
MAX_PE_CYCLES_FOR_ENDURANCE = 50

# GARBAGE COLLECTION (GC) #
GC_THRESHOLD = 0.9

# Future feature:
# Whether to run garbage collection in background during idle times
# If False, GC only runs when absolutely necessary
# BACKGROUND_GC = True

# WEAR LEVELING #
STATIC_WEAR_WINDOW = 5 # P/E cycle difference to trigger static wear leveling
STATIC_WEAR_LEVEL_CHECK_INTERVAL = 100 # Check wear leveling every 100 operations
STATIC_WEAR_LEVEL_ACTIVE_BLOCK_FRACTION = 0.15 # Minimum fraction of blocks that must be recently active to trigger static wear leveling
DYNAMIC_WEAR_WINDOW = 5 # Maximum wear difference allowed when selecting free blocks for dynamic wear leveling
ACTIVITY_WINDOW = 250 # Window to consider a block "recently active" in terms of number of operations

# SIMULATION PARAMETERS #
IDLE_PROBABILITY = 0.05
WRITE_PROBABILITY = 0.45
READ_PROBABILITY = 0.05
ERASE_PROBABILITY = 0.45
SIMULATION_TIME_UNITS = 20000 # Total time units to simulate (each unit is exactly one operation)
SIMULATION_END_THRESHOLD = 1.0 # Stop when a fraction of pages are dead
