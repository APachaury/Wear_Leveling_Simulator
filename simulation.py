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

import matplotlib.pyplot as plt # type: ignore
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
    
     # Only process write operations
    write_ops = [(i+1, time, addr, data) for i, (time, op_type, addr, data) in enumerate(workload) if op_type == 'write']
    read_ops = [(i+1, time, addr, data) for i, (time, op_type, addr, data) in enumerate(workload) if op_type == 'read']
    erase_ops = [(i+1, time, addr, data) for i, (time, op_type, addr, data) in enumerate(workload) if op_type == 'erase']
    idle_ops = [(i+1, time, addr, data) for i, (time, op_type, addr, data) in enumerate(workload) if op_type == 'idle']
    print(f"\nFound {len(write_ops)} write operations, {len(read_ops)} read operations, {len(erase_ops)} erase operations, {len(idle_ops)} idle operations in workload:")
    total_physical_pages = config.PHYSICAL_BLOCKS * config.PAGES_PER_BLOCK

    for time, op_type, addr, data in workload:
        flash_memory.simulation_time = time # Update simulation time in flash memory
        
        if op_type == 'idle':
            continue # Do nothing for idle operations - they only advance simulation time but don't count as actual flash operations
            
        if op_type == 'write':
            ftl.write(addr, data) # FTL updates mappings, finds optimal page location, and calls flash_memory.write which programs the physical page, updates states, and increments operation count
        elif op_type == 'erase':
            # Convert logical address to block ID for erase
            block_id = addr // config.PAGES_PER_BLOCK
            ftl.erase(block_id) # Erase the entire block
        elif op_type == 'read':
            ftl.read(addr) # FTL translates logical to physical address and calls flash_memory.read which accesses physical page data and updates timestamps
        
        # Perform wear leveling checks based only on operation count
        # This ensures wear leveling is triggered by actual flash operations, not just time
        if wear_leveling is not None:
            if flash_memory.operation_count % config.STATIC_WEAR_LEVEL_CHECK_INTERVAL == 0:
                if wear_leveling.should_trigger_static_wear_leveling(flash_memory.operation_count):
                    if wear_leveling.perform_static_wear_leveling(flash_memory.operation_count):
                        print(f"Static wear leveling performed at operation {flash_memory.operation_count} (time: {time})")
        
        total_dead_pages = sum(flash_memory.get_block_status(i)['dead_pages'] for i in range(config.PHYSICAL_BLOCKS))
        flash_memory.history.append((time, total_dead_pages)) # Track history of dead pages over time
        
        # Check if simulation should end (too many dead pages)
        if total_dead_pages / total_physical_pages > config.SIMULATION_END_THRESHOLD:
            print(f"Simulation ended at time {time} due to dead page threshold.")
            break
    
    # Print wear statistics
    print("\nWear Level Statistics:")
    print(f"{'With' if use_wear_leveling else 'Without'} Wear Leveling:")
    
    # Calculate statistics for written pages using FTL's tracking
    pe_cycles = []
    for physical_addr in ftl.written_pages:
        block_id = physical_addr // config.PAGES_PER_BLOCK
        page_id = physical_addr % config.PAGES_PER_BLOCK
        page = flash_memory.blocks[block_id].pages[page_id]
        pe_cycles.append(page.pe_cycles)
    
    if pe_cycles:
        avg_pe = sum(pe_cycles) / len(pe_cycles)
        max_pe = max(pe_cycles)
        min_pe = min(pe_cycles)
        print(f"Pages written to: {len(ftl.written_pages)}")
        print(f"Average PE cycles: {avg_pe:.2f}")
        print(f"Max PE cycles: {max_pe}")
        print(f"Min PE cycles: {min_pe}")
        print(f"PE cycle variance: {max_pe - min_pe}")

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
    
    # Add simulation parameters as text
    param_text = (
        f"Simulation Parameters:\n"
        f"Time Units: {config.SIMULATION_TIME_UNITS}\n"
        f"Max P/E Cycles: {config.MAX_PE_CYCLES_FOR_ENDURANCE}\n"
        f"Number of Blocks: {config.PHYSICAL_BLOCKS}\n"
        f"Pages per Block: {config.PAGES_PER_BLOCK}\n"
    )
    # Position text in upper left, outside the plot area
    plt.gcf().text(0.02, 0.98, param_text, fontsize=8, va='top')
    
    # Save plot to file
    plt.savefig('flash_memory_lifetime_comparison.png', bbox_inches='tight')
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
    
    print("\nResults have been saved to 'flash_memory_lifetime_comparison.png'")

if __name__ == "__main__":
    main()
