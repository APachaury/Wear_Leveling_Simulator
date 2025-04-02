# **Wear Leveling Simulator**

> **WARNING:** This code is not fully functional yet. It needs debugging. Please do not use it.

**Contact:** aniketpach@gmail.com  

---

## **Project Description**
This project is a **simulator** designed to visualize the effect of a **Wear Leveling Algorithm** on the lifetime of a **Flash Memory** device. It considers a **P/E (Program/Erase) cycle threshold**, beyond which memory pages are considered **bad** (*referred to as "dead pages"*).

### **Features:**
- Users can input:
  - Memory architecture
  - P/E cycle threshold
  - Various other parameters affecting the algorithm
- The simulator generates **two graphs**:
  - One showing the evolution of dead pages **with Wear Leveling**
  - One showing the evolution **without Wear Leveling**

---

## **Simulator Architecture**
The simulator is structured into multiple layers of abstraction:

### **1. `wear_leveling.py`**
- Implements the **static wear leveling algorithm**
- The **dynamic wear leveling algorithm** is implemented in `ftl.py` to reduce complexity and interdependencies

### **2. `ftl.py`**
- Represents the **Flash Translation Layer (FTL)**
- Contains the **dynamic wear leveling algorithm**

### **3. `flash_memory.py`**
- Represents **hardware-level operations**, including pages, blocks, and operations performed at a hardware level

### **4. `config.py`**
- Houses **global variables** defining thresholds and parameters specified by the user

### **5. `workload_generator.py`** *(Placeholder for now)*
- Generates a stream of memory operations, similar to what a **Flash memory controller** would process
- The actual workload characteristics are currently unknown; contributions are welcome!
  - **Email:** aniketpach@gmail.com if you can help with this

### **6. `simulation.py`**
- **Main entry point** of the simulator
- Runs the **actual simulation**

---

## **Wear Leveling Algorithm**
### **Dynamic Wear Leveling Algorithm**
- When a **write operation** is performed:
  - Identify **candidate blocks** (least worn-out blocks)
  - Choose the **first free page** from these blocks
  - If no free pages or blocks are available → **Trigger garbage collection** and retry

### **Static Wear Leveling Algorithm**
- **Trigger static wear leveling** based on:
  - The time elapsed since the last run
  - Memory activity (inactive memory remains untouched)
- If triggered, data is **moved** from **high-wear blocks** to **low-wear blocks**, based on wear difference
- If a **high-wear block has dormant data**, it remains untouched

---

## **Additional Notes**
- **The code is heavily commented and documented** for better understanding.
- **Feedback & contributions are welcome!** If you have suggestions or constructive criticism, feel free to reach out.

---
