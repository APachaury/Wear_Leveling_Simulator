## @file simulation.py
## @brief Main simulation runner comparing flash memory with and without wear leveling.
## @details This module orchestrates the entire simulation process:
## 1. Runs parallel simulations with and without wear leveling
## 2. Processes identical workloads for both scenarios
## 3. Tracks and compares memory health over time
## 4. Generates visualizations of the results
##
## Key Components:
## - run_simulation(): Runs a single simulation with or without wear leveling
## - plot_results(): Creates visualization comparing both scenarios
## - main(): Entry point that runs both simulations and generates comparisons

import matplotlib.pyplot as plt
from typing import List, Tuple
import config
from flash_memory import FlashMemory
from wear_leveling import WearLeveling
from ftl import FTL
from workload_generator import WorkloadGenerator

def run_simulation(use_wear_leveling: bool = True) -> List[Tuple[int, int]]:
    ##
    # @brief Run a flash memory simulation with configurable wear leveling.
    #
    # This simulation uses a discrete time model where:
    # 1. Time advances in fixed increments (1 unit per operation)
    # 2. Each time unit corresponds to exactly one operation (read/write/erase/idle)
    # 3. Only actual flash operations (read/write/erase) increment the operation counter
    #
    # This separation between time and operations allows us to:
    # - Track time progression for simulation purposes
    # - Count only operations that cause actual flash wear
    # - Model idle periods where time passes but no operations occur
    #
    # @param use_wear_leveling Whether to use wear leveling
    # @return List[Tuple[int, int]] History of dead pages over time
    ##
    # Initialize system components
    flash_memory = FlashMemory()
    wear_leveling = WearLeveling(flash_memory, ftl=None) if use_wear_leveling else None
    ftl = FTL(flash_memory, wear_leveling)
    
    # Connect wear leveling to FTL (circular reference resolved)
    if wear_leveling:
        wear_leveling.ftl = ftl
    
    # Generate workload
    workload_gen = WorkloadGenerator()
    workload = workload_gen.generate_sample_workload(config.SIMULATION_TIME_UNITS)
    
    # Process workload - For each operation in workload:
    # 1. FTL Layer: Handles logical address translation and garbage collection
    # 2. FlashMemory Layer: Performs physical operations and maintains state
    # 3. Block/Page Layer: Updates individual storage unit states and wear metrics
    
    for time, op_type, addr, data in workload:
        # Update simulation time in flash memory
        flash_memory.simulation_time = time
        
        if op_type == 'idle':
            # Do nothing for idle operations - they only advance simulation time but don't count as actual flash operations
            continue
            
        if op_type == 'write':
            # write: FTL updates mappings, finds optimal page location, and calls flash_memory.write which programs the physical page, updates states, and increments operation count
            ftl.write(addr, data)
        elif op_type == 'read':
            # read: FTL translates logical to physical address and calls flash_memory.read which accesses physical page data and updates timestamps
            ftl.read(addr)
        else:  # erase
            # erase_block: FTL updates mappings, free page tracking, and calls flash_memory.erase_block which erases physical pages, updates PE cycles, and marks dead pages if lifetime exceeded
            ftl.erase_block(addr)

        # Perform wear leveling checks based only on operation count
        # This ensures wear leveling is triggered by actual flash operations, not just time
        if wear_leveling is not None:
            if flash_memory.operation_count % config.STATIC_WEAR_LEVEL_CHECK_INTERVAL == 0:
                if wear_leveling.should_trigger_static_wear_leveling(flash_memory.operation_count):
                    if wear_leveling.perform_static_wear_leveling(flash_memory.operation_count):
                        print(f"Static wear leveling performed at operation {flash_memory.operation_count} (time: {time})")
            
        # Check if simulation should end (too many dead pages)
        # SIMULATION_END_THRESHOLD from config.py determines when to stop
        status = flash_memory.get_memory_status()
        if status['dead_pages'] / status['PHYSICAL_PAGES'] > config.SIMULATION_END_THRESHOLD:
            print(f"Simulation ended early at time {time} due to excessive dead pages")
            break
            
    return flash_memory.history

def plot_results(without_wl_history: List[Tuple[int, int]], 
                with_wl_history: List[Tuple[int, int]]):
    ##
    # @brief Create visualization comparing results with and without wear leveling.
    #
    # @param without_wl_history List of (time, dead_pages) for simulation without wear leveling
    # @param with_wl_history List of (time, dead_pages) for simulation with wear leveling
    #
    # Each history is a list of tuples where:
    # - tuple[0] is the time of measurement
    # - tuple[1] is the number of dead pages at that time
    ##
    plt.figure(figsize=(10, 6))
    
    # Plot both scenarios
    times_without_wl = [x[0] for x in without_wl_history]
    dead_pages_without_wl = [x[1] for x in without_wl_history]
    plt.plot(times_without_wl, dead_pages_without_wl, 'r-', label='Without Wear Leveling')
    
    times_with_wl = [x[0] for x in with_wl_history]
    dead_pages_with_wl = [x[1] for x in with_wl_history]
    plt.plot(times_with_wl, dead_pages_with_wl, 'g-', label='With Wear Leveling')
    
    plt.xlabel('Operation Count')
    plt.ylabel('Number of Dead Pages')
    plt.title('Flash Memory Lifetime Comparison')
    plt.grid(True)
    plt.legend()
    
    # Save plot to file
    plt.savefig('flash_memory_lifetime_comparison.png')
    plt.close()

def main() -> None:
    ##
    # @brief Main simulation entry point.
    # The simulation process runs without wear leveling, then with wear leveling, then generates comparison plot and prints statistics comparing both runs
    ##
    print("Starting Flash Memory Lifetime Simulation...")
    
    # Run simulation without wear leveling
    print("Running simulation without wear leveling...")
    without_wl_history = run_simulation(use_wear_leveling=False)
    
    # Run simulation with wear leveling
    print("Running simulation with wear leveling...")
    with_wl_history = run_simulation(use_wear_leveling=True)
    
    # Generate visualization
    print("Plotting results...")
    plot_results(without_wl_history, with_wl_history)
    
    # Print summary statistics
    # Access history data using list indices:
    # [0][0] = time of first measurement
    # [-1][1] = number of dead pages in last measurement
    print("\nSimulation Results:")
    print(f"Without Wear Leveling:")
    print(f"- Time to first dead page: {without_wl_history[0][0]} cycles")
    print(f"- Final dead page count: {without_wl_history[-1][1]}")
    
    print(f"\nWith Wear Leveling:")
    print(f"- Time to first dead page: {with_wl_history[0][0]} cycles")
    print(f"- Final dead page count: {with_wl_history[-1][1]}")
    
    print("\nResults have been saved to 'flash_memory_lifetime_comparison.png'")

# Main guard: Only run the simulation if this file is run directly
# If this file is imported as a module, the simulation won't auto-start
if __name__ == "__main__":
    main()
