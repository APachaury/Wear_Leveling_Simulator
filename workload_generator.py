## @file
## @brief Workload Generator for Flash Memory Simulation.
## @details This module provides a simple interface for generating basic flash operations:
## - Read: Read data from a logical address
## - Write: Write data to a logical address
## - Erase: Erase a block
## - Idle: Represent periods when no operation is happening
##
## This is a simplified placeholder version that will be replaced with a more
## sophisticated implementation later.

from typing import List, Tuple, Literal, Optional
import random
import config

## Type alias for operation types
OperationType = Literal['read', 'write', 'erase', 'idle']

## @class WorkloadGenerator
## @brief Generates realistic flash memory workloads.
## @details This class generates sequences of read/write/erase/idle operations that represent
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
    def generate_random_data(self, size: int = 128) -> bytes:
        return bytes(self.rng.getrandbits(8) for _ in range(size))
    
    ## @brief Generate a sample workload with one operation per time unit.
    ## @details In this discrete time model:
    ## - Each time unit has exactly one operation
    ## - Operations are chosen based on configured probabilities
    ## - Time advances uniformly (1 unit per operation)
    ## - The simulation runs for a fixed number of time units
    ##
    ## This is different from a variable-time model where operations might
    ## take different amounts of time to complete.
    ##
    ## @param total_time_units Total number of time units to simulate
    ## @return List of operations, each containing:
    ##         - Time (will be sequential from 0 to total_time_units-1)
    ##         - Operation type (read/write/erase/idle)
    ##         - Address (logical address for read/write, block address for erase, 0 for idle)
    ##         - Data (empty for read/erase/idle, contains data for write)
    def generate_sample_workload(self, total_time_units: int = 10000) -> List[Tuple[int, OperationType, int, bytes]]:
        workload = []
        
        # Generate one operation for each time unit
        for time in range(total_time_units):
            # Determine operation type
            if self.rng.random() < config.IDLE_PROBABILITY:
                # Generate idle operation
                workload.append((time, 'idle', 0, b''))
            else:
                # Choose between regular operations with configured weights
                op_type = self.rng.choices(
                    ['write', 'read', 'erase'], 
                    weights=[config.WRITE_WEIGHT, config.READ_WEIGHT, config.ERASE_WEIGHT]
                )[0]
                
                if op_type == 'write':
                    # Generate write to random logical address
                    addr = self.rng.randrange(config.LOGICAL_PAGES)
                    data = self.generate_random_data()
                    workload.append((time, 'write', addr, data))
                    
                elif op_type == 'read':
                    # Generate read from random logical address
                    addr = self.rng.randrange(config.LOGICAL_PAGES)
                    workload.append((time, 'read', addr, b''))
                    
                else:  # erase
                    # Generate erase on random block
                    addr = self.rng.randrange(config.PHYSICAL_BLOCKS)
                    workload.append((time, 'erase', addr, b''))
        
        return workload
