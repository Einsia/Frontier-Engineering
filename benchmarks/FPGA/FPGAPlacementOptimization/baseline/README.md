## Table of Contents

* [aug-elfPlace](#aug-elfPlace)
    - [Hybrid Placement Framework](#overview)
    - [Target Architecture](#target_arch)
* [Publication(s)](#publications)
* [Developer(s)](#developers)
* [Cloning the Repository](#cloning)
* [Build Instructions](#build)
    - [To install Python dependency](#python_dependency)
    - [To install with Docker](#Docker)
    - [To Build](#build_dreamplacefpga)
* [Benchmarks](#benchmarks)
* [Running aug-elfPlace](#running)
	- [Integration with VPR](#integrate_vpr)
* [Bug Report](#bug)
* [Copyright](#copyright)

# <a name="aug-elfPlace"></a>``aug-elfPlace``
``aug-elfPlace``, built on the [DREAMPlaceFPGA (commit 9b86a09)](https://github.com/rachelselinar/DREAMPlaceFPGA/tree/9b86a09437e08947fb65c2a0cd351d004256bcc5) framework, is a wirelength-driven generalizable flat analytical FPGA placer that consists of a global placer and packer-legalizer.
The main features of ``aug-elfPlace`` include:
 - a generalized architecture modeling that reads in the architecture-specific details and legality constraints as an additional bookshelf input file (`design.lc`);
 - employing the scalable auction algorithm to legalize a large number of digital signal processors (DSPs) and memory blocks in the design;
 - using placeholder fillers to effectively handle memory logic array block (MLAB) instances in the design;
 - employ a *partial macro representation* for carry chains;
 - enhance the instance area update and packer-legalizer algorithms for look-up tables (LUTs) and flip-flops (FFs) to ensure legal placement for different architectures; and
 - [**VPR**](https://docs.verilogtorouting.org/en/latest/vpr/)-compatible flat output placement format.

``aug-elfPlace`` can integrate with the open-source [**VPR**](https://docs.verilogtorouting.org/en/latest/vpr/) CAD tool to further improve the quality of results through annealing as part of the hybrid placement framework. Please refer to our [paper](#publications) for detailed information.

### <a name="overview"></a> Hybrid Placement Framework
The hybrid placement framework integrates a flat analytical placer such as ``aug-elfPlace`` with [**VPR**](https://docs.verilogtorouting.org/en/latest/vpr/)'s place and route tool using the [VPR legalizer](https://docs.verilogtorouting.org/en/latest/vpr/file_formats/#flat-placement-file-format-flat-place).

<p align="center">
<img src=/images/aug-elfPlace_VPR_hybrid_placement_framework.png height="500">
</p>

The [VPR legalizer](https://docs.verilogtorouting.org/en/latest/vpr/file_formats/#flat-placement-file-format-flat-place) reads in a flat placement solution and constructs a cluster-level netlist for [**VPR**](https://docs.verilogtorouting.org/en/latest/vpr/)'s placer. The [VPR legalizer](https://docs.verilogtorouting.org/en/latest/vpr/file_formats/#flat-placement-file-format-flat-place) also repairs any legality or mode-related errors in the clusters, thus allowing any external flat placer to integrate with  [**VPR**](https://docs.verilogtorouting.org/en/latest/vpr/)'s place and route tool.

The placement solution from ``aug-elfPlace`` can be routed in [**VPR**](https://docs.verilogtorouting.org/en/latest/vpr/)'s router and validated to evaluate overall performance. In addition, [**VPR**](https://docs.verilogtorouting.org/en/latest/vpr/)'s annealing-based placer can further refine the ``aug-elfPlace`` solution to improve the overall quality of results.

Please refer to our [paper](#publications) for more details on the performance of ``aug-elfPlace`` as part of the hybrid placement framework on the [Titan23 benchmarks](https://www.eecg.utoronto.ca/~kmurray/titan.html) benchmarks.

### <a name="target_arch"></a>Target Architecture
``aug-elfPlace`` can target simplified versions of the Ultrascale and Stratix-IV architectures and requires the locations of the fixed input-output (IO) and phase-locked loop (PLL) blocks to be provided as part of the input, similar to [DREAMPlaceFPGA](https://github.com/rachelselinar/DREAMPlaceFPGA).

<p align="center">
<img src=/images/US_SIV_arch.png height="500">
</p>

FPGA architectures consist of DSP blocks and different memory blocks - BRAM, M9K, and M144K, with Slice blocks that consist of LUT, FF, and adder instances. 
> Carry adder instances in the Ultrascale architecture are not shown in the Figure, as the benchmarks do not contain any.

Slice blocks are configurable logic blocks (CLBs) in Ultrascale architecture and logic array blocks (LABs) in Stratix-IV architecture. The architectures differ significantly in the configuration of the Slice blocks and the legality constraints for LUTs and FFs.

#### Simplified Ultrascale Architecture 
- The [ISPD'2016 benchmarks](http://www.ispd.cc/contests/16/FAQ.html) targeting a simplified [AMD/Xilinx Ultrascale](https://docs.amd.com/v/u/en-US/ds890-ultrascale-overview) architecture.  *``aug-elfPlace`` can be run on GPU and CPU for Ultrascale-like architectures.*

#### Simplified Stratix-IV Architecture 
- The [Titan23 benchmarks](https://www.eecg.utoronto.ca/~kmurray/titan.html) targeting a simplified [Intel/Altera Stratix-IV](https://www.intel.com/content/www/us/en/content-details/654799/stratix-iv-device-handbook.html) architecture. *Due to large packer-legalizer runtime for the Stratix-IV-like architecture, ``aug-elfPlace`` is run on CPU.*

> Note: ``aug-elfPlace`` is not tested on the AMD/Xilinx Ultrascale+ or other architecture.

## <a name="publications"></a>Publication(s) 

* Rachel Selina Rajarathnam, Kate Thurmer, Vaughn Betz, Mahesh A. Iyer, and [David Z. Pan](http://users.ece.utexas.edu/~dpan), "**Better Together: Combining Analytical and Annealing Methods for FPGA Placement**," *34th International Conference on Field-Programmable Logic and Applications (FPL)*, 2024 (accepted).

## <a name="developers"></a>Developer(s)

- Rachel Selina Rajarathnam, [UTDA](https://www.cerc.utexas.edu/utda), ECE Department, The University of Texas at Austin

## <a name="cloning"></a>Cloning the Repository

External dependencies are the same as [DREAMPlaceFPGA](https://github.com/rachelselinar/DREAMPlaceFPGA/tree/9b86a09437e08947fb65c2a0cd351d004256bcc5?tab=readme-ov-file#dependencies).

To pull git submodules in the root directory
```
git submodule init
git submodule update
```

Alternatively, pull all the submodules when cloning the repository. 
```
git clone --recursive https://github.com/rachelselinar/aug-elfPlace.git
```

## <a name="build"></a>Build Instructions

### <a name="python_dependency"></a>To install Python dependency 

There is an alternative way to install ``aug-elfPlace`` using Docker. If you want to use Docker, skip this step and go to [Docker installation](#Docker).

At the root directory:
```
pip install -r requirements.txt 
```
> For example, if the repository was cloned in directory ***~/Downloads***, then the root directory is ***~/Downloads/aug-elfPlace***

> You can also use a [python virtual environment](https://docs.python.org/3/library/venv.html) to install all the required packages to run ``aug-elfPlace``

### <a name="Docker"></a>To install with Docker

You can use the Docker container to avoid building all the dependencies yourself.

1. Install Docker on [Linux](https://docs.docker.com/install/) (Win and Mac are not tested).
2. To enable the GPU features, install [NVIDIA-docker](https://github.com/NVIDIA/nvidia-docker); otherwise, skip this step.
3. Get the docker image using one of the options
    Build the image locally.
    ```
    docker build . --file Dockerfile --tag <username>/dreamplacefpga:1.0
    ```
    Replace `<username>` with a username, for instance, 'utda_placer.'
4. Enter the bash environment of the container.
    Mount the repo and all the Designs into the Docker, which allows the Docker container to access and modify these files directly.

    To run on a Linux machine without GPU:
    ```
    docker run -it -v $(pwd):/aug-elfPlace <username>/dreamplacefpga:1.0 bash
    ```
    To run on a Linux machine with GPU: (Docker verified on NVIDIA GPUs with compute capability 6.1, 7.5, and 8.0)
    ```
    docker run --gpus 1 -it -v $(pwd):/aug-elfPlace <username>/dreamplacefpga:1.0 bash
    ```

    For example, to run on a Linux machine without GPU:
    ```
    docker run -it -v $(pwd):/aug-elfPlace utda_placer/dreamplacefpga:1.0 bash
    ```
5. Go to the `aug-elfPlace` directory in the Docker, which is the root directory of the project
    ```
    cd /aug-elfPlace
    ```


### <a name="build_dreamplacefpga"></a>To Build 

At the root directory, 
```
mkdir build 
cd build 
cmake .. -DCMAKE_INSTALL_PREFIX=path_to_root_dir
make
make install
```

If you are using Docker, use the following at the root directory,
 ```
rm -rf build
mkdir build 
cd build 
cmake .. -DCMAKE_INSTALL_PREFIX=/aug-elfPlace -DPYTHON_EXECUTABLE=$(which python)
make
make install
```

Third-party submodules are automatically built except for [Boost](https://www.boost.org).

> For example,

> ***~/Downloads/aug-elfPlace:*** *mkdir build; cd build*

> ***~/Downloads/aug-elfPlace/build:***  *cmake . . -DCMAKE_INSTALL_PREFIX=~/Downloads/aug-elfPlace*

> ***~/Downloads/aug-elfPlace/build:*** *make; make install*

> The directory ***~/Downloads/aug-elfPlace/build*** is the install dir

When packages or parser code are changed, the contents of the ***build*** directory must be deleted for a clean build and proper operation.
```
rm -r build
```
> For example,

> ***~/Downloads/aug-elfPlace:*** *rm -r build*

For cmake options, refer to [DREAMPlaceFPGA](https://github.com/rachelselinar/DREAMPlaceFPGA/tree/main?tab=readme-ov-file#cmake).

## <a name="benchmarks"></a> Benchmarks

``aug-elfPlace`` only accepts inputs in the [Bookshelf](./benchmarks/sample_ispd2016_benchmarks/README) format and requires IO/PLL locations to be fixed.
- 12 designs for *AMD/Xilinx Ultrascale Architecture* in the updated bookshelf format with fixed IOs are provided from the [ISPD'2016 contest](http://www.ispd.cc/contests/16/FAQ.html).
- [Titan23](https://www.eecg.utoronto.ca/~kmurray/titan.html) designs based on the simplified *Intel/Altera Stratix-IV Architecture*, generated by [VPR](https://docs.verilogtorouting.org/en/latest/vpr/), are included in bookshelf format.

All the designs are in the [benchmarks](./benchmarks) directory, and sample JSON configuration files are in the [test](./test) directory. For the complete list of available options in the JSON file, please refer to [paramsFPGA.json](./dreamplacefpga/paramsFPGA.json). 

## <a name="running"></a>Running aug-elfPlace

Before running, ensure that all python dependent packages have been installed. 
Go to the ***root directory*** and run with the JSON configuration file.  
```
python dreamplacefpga/Placer.py <benchmark>.json
```
> Run from ***~/Downloads/aug-elfPlace*** directory

For example:
```
python dreamplacefpga/Placer.py test/FPGA01.json
```
> ***~/Downloads/aug-elfPlace:*** *python dreamplacefpga/Placer.py test/FPGA01.json*

> If you are not using the GPU, change the gpu flag in the *.json file to 0.

Unit tests for some of the pytorch operators are provided. For instance, to run the unit test for hpwl, use the below command:
```
python unitest/ops/hpwl_unitest.py
```
> Note: If your machine does not have an NVIDIA GPU, set the '***gpu***' flag in the JSON configuration file to '***0***' to run on the CPU.

### <a name="integrate_vpr"></a>Integration with [VPR](https://docs.verilogtorouting.org/en/latest/vpr/)
- Generate flat placement solution from ``aug-elfPlace`` in [VPR compatible format](https://docs.verilogtorouting.org/en/latest/vpr/file_formats/#flat-placement-file-format-flat-place) as a *.pl* file:
```
<node_name>  x  y  s  z  <node_type>
```
Where '*s*' refers to subtile location, set to zero '*s=0*' for IO/PLL instances, whereas '*z=0*' for DSP/memory/Slice instances.

- Use [VPR legalizer](https://docs.verilogtorouting.org/en/latest/vpr/file_formats/#flat-placement-file-format-flat-place) to construct a cluster-level netlist for VPR after fixing any legality or mode-related failures. A '*.net*' clustered netlist and '*.fix_clusters*' placement file is generated from the VPR legalizer's output.

- To validate the placement solution without refinement in VPR, use the '*.fix_clusters*' file generated as '*.place*' input placement file to VPR. For details, refer to this [comment](https://github.com/verilog-to-routing/vtr-verilog-to-routing/issues/2484#issuecomment-1938993673). VPR router is run on the input placement followed by validation.

To refine the placement solution in VPR, list only IO/PLL instances in the '*.fix_clusters*' file and let the VPR placer refine the placement before routing and validation.
> Note: Integration with VPR is verified only for the Titan23 benchmarks.

## <a name="bug"></a>Bug Report

Please file an [issue](https://github.com/rachelselinar/aug-elfPlace/issues) to report a bug.

## <a name="copyright"></a>Copyright

This software is released under a BSD 3-Clause "New" or "Revised" License. Please refer to [LICENSE](./LICENSE) for details.

