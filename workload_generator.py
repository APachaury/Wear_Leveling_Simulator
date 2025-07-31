## @file
## @brief Workload Generator for Flash Memory Simulation.
## @details This module provides a simple interface for generating basic flash operations:
## - Read: Read data from a logical address
## - Write: Write data to a logical address
## - Idle: Represent periods when no operation is happening
##
## This is a simplified placeholder version that will be replaced with a more
## sophisticated implementation later.

from typing import List, Tuple, Literal, Optional
import random
import config

## Type alias for operation types
OperationType = Literal['read', 'write', 'idle', 'erase']

## @class WorkloadGenerator
## @brief Generates realistic flash memory workloads.
## @details This class generates sequences of read/write/idle operations that represent
## realistic usage patterns for flash memory. It uses a time-based model where:
##
## 1. Time advances in discrete steps (1 unit per operation)
## 2. Each time unit has exactly one operation (read, write, erase, or idle)
## 3. Time and operations are separate concepts:
##    - Time represents the chronological progression of the simulation
##    - Operations count only tracks actual flash operations (read/write/erase)
##
## This separation allows for more realistic modeling of flash memory wear, which
## depends on operations performed, not just time elapsed.
class WorkloadGenerator:
    
    ## @brief Initialize the workload generator.
    ## @param seed Random seed for reproducible workloads (default: None)
    def __init__(self, seed: Optional[int] = None) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.operation_count = 0
    
    ## @brief Generate random data for write operations.
    ## @param size Size of data in bytes (default: 128)
    ## @return Random bytes
    def generate_random_data(self, size: int = config.PAGE_SIZE) -> bytes:
        return bytes(self.rng.getrandbits(8) for _ in range(size))
    
    ## @brief Generate a sample workload with one operation per time unit.
    ## @details In this discrete time model:
    ## - Each time unit has exactly one operation
    ## - Operations are chosen based on configured probabilities
    ## - Time advances uniformly (1 unit per operation)
    ## - The simulation runs for a fixed number of time units
    ##
    ## @param total_time_units Total number of time units to simulate
    ## @return List of operations, each containing:
    ##         - Time (will be sequential from 0 to total_time_units-1)
    ##         - Operation type (read/write/idle/erase)
    ##         - Address (logical address for read/write, 0 for idle)
    ##         - Data (empty for read/idle, contains data for write)
    def generate_sample_workload(self, total_time_units: int) -> List[Tuple[int, OperationType, int, bytes]]:
        workload = []
        
        # Generate one operation for each time unit
        for time in range(total_time_units):
            rand = self.rng.random()
            
            if rand < config.IDLE_PROBABILITY:
                workload.append((time, 'idle', 0, b'')) # 30% idle operations
            elif rand < config.IDLE_PROBABILITY + config.WRITE_PROBABILITY:
                # Generate write to random logical address (35% of operations)
                addr = self.rng.randrange(config.LOGICAL_PAGES)
                data = self.generate_random_data()
                workload.append((time, 'write', addr, data))
            elif rand < config.IDLE_PROBABILITY + config.WRITE_PROBABILITY + config.ERASE_PROBABILITY:
                # Generate erase to random logical address (10% of operations)
                addr = self.rng.randrange(config.LOGICAL_PAGES)
                workload.append((time, 'erase', addr, b''))
            else:
                # Generate read from random logical address (remaining 35%)
                addr = self.rng.randrange(config.LOGICAL_PAGES)
                workload.append((time, 'read', addr, b''))
        
        return workload
