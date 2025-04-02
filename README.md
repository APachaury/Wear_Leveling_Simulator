# Wear_Leveling_Simulator
WARNING: This code does not work yet. It needs to be debugged. Please do not use it.
Contact: aniketpach@gmail.com

Project Description:
This project is a simulator to visualize the effect of a Wear Leveling Algorithm on the lifetime of a Flash Memory device. It considers a P/E cycle threshold, above which pages of memory are considered to be bad (which I call "dead pages").
The simulator takes as inputs from the user the memory architecture, P/E cycle threshold, and various other parameters which affect the algorithm.
The simulator produces as an output two graphs, which plot how the number of "dead" pages evolve as time, with and without the Wear Leveling algorithm.

The architecture of the simulator itself is divided into multiple layers of abstraction -
1. wear_leveling.py (This is the static wear leveling algorithm. The dynamic wear leveling is implemented in ftl.py, because it reduces complexity and inter-dependencies in the code.)
2. ftl.py (This is the FTL - Flash Translation Layer. It also contains the dynamic wear leveling algorithm.)
3. flash_memory.py (This represents the hardware itself, such as pages and blocks, and the operations that are performed at a hardware level.)

config.py houses all the global variables that represent the various thresholds and parameters to be defined as user inputs.
workload_generator.py is to generate a stream of operations that the memory must perform, like what a Flash memory controller in a processor would take as an input. Note that this file is a placeholder for now. I do not know how the actual workload of a Flash memory device might look like, and I wish to find out so that I can implement it. Please email me at aniketpach.gmail.com if you can help with this.
simulation.py where is the actual simulation is run, and is the entry point to the simulator. It houses the main function.


Wear Leveling Algorithm:
Dynamic Wear Leveling Algorrithm: Whenever a write operation is to be performed, we determine a set of candidates blocks, which are among the blocks with the least wear in the memory, and we choose to write to the first free page from these candidate blocks. If there are no free pages or free blocks, we trigger garbage collection and try again.
Static Wear Leveling Algorithm: We first decide whether we should even trigger run static wear leveling and move data around, based on how long it has been since we last triggered static wear leveling. We also do not try wear leveling if the Flash memory has not been active for some time, since not much would have changed. If we do trigger static wear leveling, we move data from blocks woth high wear to blocks with low wear, based on the difference in their wear. If a high wear block has not been active for long enough, we leave it as it is, since the data is dormant.


Note that the code is heavily commented and documented, for my own reference.
Any suggestions or constructive criticism is most welcome.
