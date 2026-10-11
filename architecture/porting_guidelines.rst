.. _porting_guidelines:

##################
Porting guidelines
##################
This document has two parts:

* :ref:`porting_new_device` describes how to get OP-TEE up and running on a new
  device with initial xtest validation passing.

* :ref:`porting_production` describes the missing pieces that must be addressed
  to use OP-TEE in a real secure product.

We are trying our best to implement full end to end security in OP-TEE in a
generic way, but due to the nature of devices being different, NDA etc, it is
not always possible for us to do so and in those cases, we most often try to
write a generic API, but we will just stub the code. This porting guideline
highlights the missing pieces that must be addressed in a real secure consumer
device. Hopefully we will sooner or later get access to devices where we at
least can make reference implementations publicly available to everyone for the
missing pieces we are talking about here.

.. _porting_new_device:

Part 1: Porting OP-TEE to a new device
**************************************
This part describes how to add support for a new device to OP-TEE and how
to get it up and running.

.. _porting_boot_flow:

Boot flow and prerequisites
===========================
Before adding a platform it is useful to know how OP-TEE will be loaded and
how it communicates with the normal world on the device. The combinations
supported by OP-TEE are:

- **With Trusted Firmware A** (``CFG_WITH_ARM_TRUSTED_FW=y``). OP-TEE is the
  BL32 image loaded by TF-A, and TF-A runs the secure monitor at EL3. TF-A is
  built with ``SPD=opteed`` for the OP-TEE SMC ABI.
- **With FF-A**. OP-TEE runs as the Secure Partition Manager Core (SPMC) at
  S-EL1 (``CFG_CORE_SEL1_SPMC=y``), as a secure partition under an SPMC at
  S-EL2 such as Hafnium (``CFG_CORE_SEL2_SPMC=y``), or together with the TF-A
  EL3 SPMC (``CFG_CORE_EL3_SPMC=y``). See :doc:`spmc`.
- **Without Trusted Firmware A** on Armv7-A (``CFG_WITH_ARM_TRUSTED_FW=n``).
  OP-TEE contains the secure monitor and implements PSCI itself (see
  :ref:`porting_power_management`).

The boot loader passes boot arguments to OP-TEE, for example the address of
the device tree. Which arguments are used depends on the configuration above.
The binaries that the boot loader loads are described in
:ref:`porting_binaries`.

Things to have at hand before starting:

- The memory map of the device: where secure DRAM (and SRAM) for OP-TEE is
  placed, where non-secure DRAM is, and the base addresses of the console UART
  and the interrupt controller.
- The boot loader configuration that loads OP-TEE, and how it configures the
  memory firewall (see :ref:`porting_production`).

.. _add_a_new_platform:

Add a new platform
==================
The first thing you need to do after you have decided to port OP-TEE to another
device is to add a new platform device. That can either be adding a new platform
variant (``PLATFORM_FLAVOR``) if it is a device from a family already supported,
or it can be a brand new platform family (``PLATFORM``). Typically this initial
setup involve configuring UART, memory addresses etc. For simplicity let us call
our fictive platform for "gendev" just so we have something to refer to when
writing examples further down.

core/arch/<arch>
----------------
In ``core/arch/arm`` and ``core/arch/riscv`` you will find all the currently
supported devices. That is where you are supposed to add a new platform or
modify an existing one. Typically you will find this set of files in a specific
platform folder:

.. code-block:: bash

    $ ls
    conf.mk  main.c  platform_config.h  sub.mk

So for the gendev platform it means that the files should be placed in this
folder:

.. code-block:: bash

    core/arch/arm/plat-gendev

**conf.mk**

This is the device specific makefile where you define configurations unique to
your platform. This mainly comprises two things:

- OP-TEE configuration variables (``CFG_``), which may be assigned values in
  two ways. ``CFG_FOO ?= bar`` should be used to provide a default value that
  may be modified at compile time. On the other hand, variables that must be
  set to some value and cannot be modified should be set by: ``$(call
  force,CFG_FOO,bar)``.

- Compiler flags for the TEE core, the user mode libraries and the Trusted
  Applications, which may be added to macros used by the build system. Please
  see :ref:`configuration_and_flags` and similar sections on that page.

It is recommended to use a existing platform configuration file as a starting
point. For instance, `core/arch/arm/plat-hikey/conf.mk`_.

The platform ``conf.mk`` file should at least define the default platform flavor
for the platform, the CPU configuration (by including a file from
``core/arch/arm/cpu``) and the number of cores, the console driver, the secure
time source, whether OP-TEE runs together with Trusted Firmware A, and the
secure memory and static shared memory locations:

.. code-block:: make

    PLATFORM_FLAVOR ?= gendev

    include core/arch/arm/cpu/cortex-armv8-0.mk

    $(call force,CFG_TEE_CORE_NB_CORE,4)
    $(call force,CFG_8250_UART,y)
    $(call force,CFG_SECURE_TIME_SOURCE_CNTPCT,y)
    $(call force,CFG_WITH_ARM_TRUSTED_FW,y)
    $(call force,CFG_GIC,y)

    CFG_NUM_THREADS ?= 4
    CFG_CRYPTO_WITH_CE ?= y

    # Platform specific option: UART instance used as secure console
    CFG_CONSOLE_UART ?= 0

    # Secure memory used by OP-TEE (TEE core and TA RAM)
    CFG_TZDRAM_START ?= 0x60000000
    CFG_TZDRAM_SIZE ?= 0x02000000
    # Non-secure static shared memory
    CFG_SHMEM_START ?= 0x08000000
    CFG_SHMEM_SIZE ?= 0x00400000
    # Optional: size of the TEE core part of CFG_TZDRAM
    CFG_TEE_RAM_VA_SIZE ?= 0x00400000

``CFG_TZDRAM_START``, ``CFG_TZDRAM_SIZE``, ``CFG_SHMEM_START`` and
``CFG_SHMEM_SIZE`` are mandatory when ``platform_config.h`` includes
``mm/generic_ram_layout.h`` (see below).

The console driver is selected with the ``CFG_`` option of the UART driver,
``CFG_8250_UART`` in the example. The UART drivers and their options are listed
in ``core/drivers/sub.mk``.

A platform can also define its own configuration options. ``CFG_CONSOLE_UART``
in the example is such an option: it is not a generic OP-TEE option, and the
platform's ``platform_config.h`` uses it to select the base address of the UART
that is used as console.

Many options have defaults in ``mk/config.mk`` or are derived from the CPU
architecture, and do not have to be set in the platform ``conf.mk``.

**main.c**

This platform specific file contains the registration of the memory areas that
OP-TEE needs to map, the console initialization and, if the platform has an
interrupt controller, its initialization. For our gendev device it could look
like this (here we are excluding the necessary license header to save some
space):

.. code-block:: c

    #include <console.h>
    #include <drivers/gic.h>
    #include <drivers/serial8250_uart.h>
    #include <kernel/boot.h>
    #include <mm/core_mmu.h>
    #include <platform_config.h>

    static struct serial8250_uart_data console_data;

    /* Peripherals that OP-TEE maps */
    register_phys_mem_pgdir(MEM_AREA_IO_NSEC, CONSOLE_UART_BASE,
                            SERIAL8250_UART_REG_SIZE);
    register_phys_mem_pgdir(MEM_AREA_IO_SEC, GICD_BASE, GIC_DIST_REG_SIZE);
    register_phys_mem_pgdir(MEM_AREA_IO_SEC, GICC_BASE, GIC_CPU_REG_SIZE);

    /* Non-secure DDR, used for dynamic shared memory */
    register_ddr(DRAM0_BASE, DRAM0_SIZE);

    void plat_console_init(void)
    {
    	serial8250_uart_init(&console_data, CONSOLE_UART_BASE,
    			     CONSOLE_UART_CLK_IN_HZ, CONSOLE_BAUDRATE);
    	register_serial_console(&console_data.chip);
    }

    void boot_primary_init_intc(void)
    {
    	gic_init(GICC_BASE, GICD_BASE);
    }

    void boot_secondary_init_intc(void)
    {
    	gic_init_per_cpu();
    }

The functions above override weak default implementations:

- ``plat_console_init()`` sets up the secure console (see
  :ref:`porting_console`).
- ``boot_primary_init_intc()`` and ``boot_secondary_init_intc()`` initialize
  the interrupt controller on the primary core and on each secondary core. On
  GICv3 ``gic_init_v3()`` is used instead of ``gic_init()``.

``register_phys_mem_pgdir()`` registers a memory area that OP-TEE maps.
``register_ddr()`` describes the non-secure DDR. OP-TEE accepts the parts of it
that do not overlap with secure memory as non-secure shared memory. As an
alternative, the memory can be described by the device tree that is passed to
OP-TEE (see :ref:`device_tree`).

**Entry points and handlers**

The SMC, interrupt and power management entry points of OP-TEE are
implemented in the core. A platform does not register a handler table.
Instead it overrides weak functions when it needs platform specific
behavior:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Event
     - Handled by
   * - Standard (yielding) SMC
     - ``tee_entry_std()``. An override calls ``__tee_entry_std()`` for the
       functions it does not handle.
   * - Fast SMC
     - ``tee_entry_fast()``. An override handles its platform specific
       function IDs and calls ``__tee_entry_fast()`` for the others.
   * - Secure (native) interrupt
     - ``interrupt_main_handler()``, provided by the interrupt controller
       driver, for example the GIC driver (``CFG_GIC=y``). Without it, OP-TEE
       panics on the first secure interrupt. Drivers register handlers for
       individual interrupts with ``interrupt_add_handler()`` and related
       functions (see :ref:`interrupt_handling`).
       ``CFG_CORE_IRQ_IS_NATIVE_INTR`` selects whether native interrupts are
       signaled as FIQ or IRQ.
   * - CPU on, off, suspend, resume, system off and reset
     - See :ref:`porting_power_management`.
   * - SMC handled in the secure monitor (``CFG_WITH_ARM_TRUSTED_FW=n``)
     - ``sm_platform_handler()``, called when ``CFG_SM_PLATFORM_HANDLER=y``.
       SMCs that it does not handle are passed on to OP-TEE.

Platform specific SMC functions are reachable from the normal world, see
:ref:`ree_tee_interface`.

**platform_config.h**

This is a mandatory header file for every platform, since there are several
files relying upon the existence of this particular file. It defines base
addresses of peripherals, clocks and memory that are not configured in
``conf.mk``. Most platforms include ``mm/generic_ram_layout.h``, which derives
the memory layout macros from the ``CFG_`` memory options in ``conf.mk`` (see
:ref:`Memory layout <porting_memory_layout>` below). Our fictive gendev could look like this:

.. code-block:: c

    #ifndef PLATFORM_CONFIG_H
    #define PLATFORM_CONFIG_H

    #include <mm/generic_ram_layout.h>

    /* Make stacks aligned to data cache line length */
    #define STACK_ALIGNMENT		64

    /* 8250 UART */
    #define UART0_BASE		0xcafe0000
    #define UART1_BASE		0xcafe1000

    #if (CFG_CONSOLE_UART == 0)
    #define CONSOLE_UART_BASE	UART0_BASE
    #elif (CFG_CONSOLE_UART == 1)
    #define CONSOLE_UART_BASE	UART1_BASE
    #else
    #error Unknown console UART
    #endif

    #define CONSOLE_BAUDRATE	115200
    #define CONSOLE_UART_CLK_IN_HZ	19200000

    /* GIC */
    #define GICD_BASE		0x2f000000
    #define GICC_BASE		0x2c000000

    /* Non-secure DDR */
    #define DRAM0_BASE		0x40000000
    #define DRAM0_SIZE		0x80000000

    #endif /* PLATFORM_CONFIG_H */

Note that parts of the DDR typically will need to be shared with normal world,
so there is need for some kind of memory firewall for this (more about that
further down).

.. _porting_memory_layout:

**Memory layout**

The memory layout is set with the following ``conf.mk`` options when
``platform_config.h`` includes ``mm/generic_ram_layout.h``. The header file
documents the resulting layout with and without ``CFG_WITH_PAGER``.

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - ``conf.mk`` option
     - Description
   * - ``CFG_TZDRAM_START``, ``CFG_TZDRAM_SIZE`` (mandatory)
     - Secure DRAM used by OP-TEE. Without the pager the TEE core is placed at
       the start of it. The rest of it is used for TA memory, so TA memory does
       not need a separate definition.
   * - ``CFG_TEE_RAM_VA_SIZE`` (optional)
     - Size of the TEE core memory.
   * - ``CFG_TEE_LOAD_ADDR`` (optional)
     - Load address of the TEE core. Defaults to the start of the TEE core
       memory.
   * - ``CFG_TZSRAM_START``, ``CFG_TZSRAM_SIZE`` (optional, pager only)
     - On-chip secure SRAM used by the pager. If not set with
       ``CFG_WITH_PAGER=y``, the SRAM is emulated at the start of
       ``CFG_TZDRAM``.
   * - ``CFG_SHMEM_START``, ``CFG_SHMEM_SIZE`` (mandatory)
     - Non-secure static shared memory. Dynamic shared memory uses the
       non-secure DDR described with ``register_ddr()`` or the device tree
       instead.

A platform can also define the layout macros by hand in ``platform_config.h``
instead of including ``mm/generic_ram_layout.h``, as some existing platforms
do.

**sub.mk**

This file lists the source files of the platform and the include directories:

.. code-block:: make

    global-incdirs-y += .
    srcs-y += main.c

.. _porting_console:

Console
-------
The secure console is the first thing to get working on a new device, since
the boot log, ``EMSG()``/``IMSG()`` output and abort and panic dumps (see
:ref:`abort_dumps`) are printed on it.

- ``plat_console_init()`` is called early during boot. The weak default does
  nothing, so without a platform implementation OP-TEE runs without console
  output. Other console backends, such as semihosting and the FF-A console, are
  selected with ``CFG_`` options instead.
- The console UART must be mapped with ``register_phys_mem_pgdir()``, see
  ``main.c`` above.
- With ``CFG_DT=y``, OP-TEE later switches the console to the UART given by
  ``stdout-path`` in the ``/secure-chosen`` node, or in ``/chosen`` if there is
  no ``/secure-chosen`` node, if a matching driver is enabled. If the node
  exists but has no ``stdout-path`` property, OP-TEE turns the console off.
- ``CFG_TEE_CORE_LOG_LEVEL`` selects how much is printed (see
  :ref:`porting_production_build`).

.. _porting_binaries:

Binaries
--------
Building OP-TEE results in a few binaries in the out directory.  Which
binaries are used depends on how OP-TEE is loaded into memory.

.. list-table:: Binaries generated by default
   :header-rows: 1

   * - Name
     - Description
   * - tee.elf
     - The main ELF file. All other binaries are created with this
       as input.
   * - tee-header_v2.bin
     - Combined header for tee-pager_v2.bin and tee-pageable_v2.bin. Used
       by TF-A as bl32.bin to describe bl32_extra1.bin and bl32_extra2.bin.
       Passed to TF-A with BL32=<filename>.bin when building the FIP.
   * - tee-pager_v2.bin
     - Raw binary for the unpaged and init parts of OP-TEE. Used by TF-A as
       bl32_extra1.bin, requires tee-header_v2.bin. Passed to TF-A with
       BL32_EXTRA1=<filename>.bin
   * - tee-pageable_v2.bin
     - Raw binary for the paged part of OP-TEE. Used by TF-A as
       bl32_extra2.bin, requires tee-header_v2.bin. Passed to TF-A with
       BL32_EXTRA2=<filename>.bin. This file is empty and the parameter is
       optional if OP-TEE is built with CFG_WITH_PAGER=n
   * - tee.bin
     - The original binary with a header and combined init, paged, and
       unpaged parts
   * - tee.dmp
     - A dump of the ELF file using ``objdump -lxd``
   * - tee-raw.bin
     - Raw binary suitable to copy into physical memory where OP-TEE
       be can executed from. Used by Hafnium to load OP-TEE, passed via
       sp_layout.json.

.. list-table:: Binaries generated only if given as targets to make
   :header-rows: 1

   * - Name
     - Description
   * - tee.srec
     - Dump an SREC file from tee-raw.bin using ``objcopy -I binary -O srec``
   * - tee-pager.bin
     - Legacy raw binary with unpaged sections.
   * - tee-pageable.bin
     - Legacy raw binary with paged and init sections.

Hardware Crypto IP
==================
By default OP-TEE uses a software crypto library (currently mbed TLS and
LibTomCrypt) and you have the ability to enable Crypto Extensions that were
introduced with ARMv8-A (if the device is capable of that). Some of the devices
supported in OP-TEE OS repository have hardware crypto capabilities. A
framework, named drvcrypt has been designed to integrate them. The
``drvcrypt_register_*()`` API functions allow drivers to register support for
given cryptographic operations in OP-TEE core crypto API. Our
:ref:`cryptographic_implementation` page describes in detail how the Crypto API
is integrated.

.. _porting_power_management:

Power Management / PSCI
=======================
How power management requests reach OP-TEE depends on whether OP-TEE runs
together with Trusted Firmware A:

- With ``CFG_WITH_ARM_TRUSTED_FW=y``, TF-A implements PSCI and forwards the
  CPU and system power events to OP-TEE. The platform can override the weak
  ``thread_cpu_*_handler()`` and ``thread_system_*_handler()`` functions that
  handle CPU off, suspend and resume, and system off and reset. The defaults do
  nothing.
- With ``CFG_WITH_ARM_TRUSTED_FW=n`` (Armv7-A), OP-TEE contains the secure
  monitor and implements PSCI itself. The platform implements the ``psci_*()``
  functions for the PSCI calls it supports.

Drivers and core services register suspend and resume callbacks with
``register_pm_driver_cb()`` and ``register_pm_core_service_cb()``. The
callbacks run when the platform calls ``pm_change_state()``. The default
handlers do not call it, so a platform that needs the callbacks calls
``pm_change_state()`` from its own handlers.

.. _porting_device_tree:

Device tree
===========
OP-TEE can use a device tree in two ways, both enabled with ``CFG_DT=y``
(default ``n``):

- An external device tree passed by the boot loader. OP-TEE adds nodes for
  the normal world to it, such as the ``linaro,optee-tz`` firmware node when
  FF-A is not used, and ``reserved-memory`` nodes for the secure memory and the
  static shared memory.
- An embedded device tree describing the secure hardware, compiled into the
  core when ``CFG_EMBED_DTB_SOURCE_FILE`` names a DTS file in
  ``core/arch/$(ARCH)/dts``.

``CFG_DT`` is forced to ``y`` when an embedded DTB or an SPMC configuration is
used. See :ref:`device_tree` for the details.

.. _porting_normal_world:

Normal world integration
========================
The normal world side of OP-TEE consists of:

- The OP-TEE driver in the Linux kernel (``CONFIG_OPTEE``, see
  :ref:`linux_kernel`). Without FF-A it finds OP-TEE through the
  ``linaro,optee-tz`` device tree node, which also selects ``smc`` or ``hvc``
  as the calling method. With FF-A it uses the FF-A transport.
- ``tee-supplicant`` and ``libteec`` from :ref:`optee_client`.
  ``tee-supplicant`` loads TAs from the REE file system and serves REE file
  system requests from OP-TEE. It also serves RPMB requests unless the kernel
  handles them itself.

.. _porting_validation:

Validation with xtest
=====================
``xtest`` from :ref:`optee_test` runs on the device and tests the OP-TEE core,
the GlobalPlatform APIs and the normal world integration. It requires the
OP-TEE driver, a running ``tee-supplicant`` and the test TAs installed in the
TA load path. See :ref:`optee_test_run_xtest` for how to run it.

Some tests use embedded test pseudo TAs in OP-TEE, which are enabled with
``CFG_ENABLE_EMBEDDED_TESTS=y``.

``xtest`` validates functionality. It does not test the security properties
described in :ref:`porting_production`. When OP-TEE aborts or panics, see
:ref:`abort_dumps` for how to interpret the dump.

.. _official_board_support:

Official board support in OP-TEE?
=================================
We do encourage everyone to submit their board support to the OP-TEE project
itself, so it becomes part of the official releases and will be maintained by
the OP-TEE community itself. If you intend to do so, then there are a few more
things that you are supposed to do.

**Update platforms supported**

There is a section at the :ref:`platforms_supported` page that lists all devices
officially supported in OP-TEE, that is where you also shall list your device.
It should contain the name of the platform, then composite ``PLATFORM`` flag and
whether the device is publicly available or not. If there is a product page on
the internet for the device, please also create a link when writing the device
name.

**Update the CI configuration**

OP-TEE uses GitHub Actions for continuous integration. The list of build
configurations is in the `.github/workflows/ci.yml
<https://github.com/OP-TEE/optee_os/blob/master/.github/workflows/ci.yml>`_
file. Please add your platform to the build matrix so that it gets built
whenever someone opens a pull request. A platform is added either as a new
matrix entry or as another build command in the ``make_commands`` list of an
existing entry:

.. code-block:: yaml

    - name: <arch> <platform>
      make_commands: |
        _make PLATFORM=<platform-name>

**Maintainer**

If you are submitting the board support upstream we are going to ask you to
become the maintainer for the device you have added. This means that you should
also update the MAINTAINERS_ file accordingly. By being a maintainer for a
device you are responsible to keep it up to date and you will be asked every
quarter as part of the OP-TEE release schedule to test your device running the
latest OP-TEE software.

**Update build.git and manifest.git**

This isn't strictly necessary, but we are trying to create and maintain OP-TEE
developer builds that should make it easy to setup, build and deploy OP-TEE on
various devices. We encourage all maintainers to do the same for the boards they
are in charge of. Therefore please consider creating a new :ref:`manifest` (and
a new ``*.mk`` in :ref:`build`) for the device you have added to OP-TEE.

.. _porting_production:

Part 2: Hardening for production
********************************
This part describes the security relevant parts of a port that are needed
to use OP-TEE in a product. The sections follow the order of the
:ref:`porting_checklist` at the end of this part.

.. _platform_ports:

Platform ports
==============
OP-TEE is a reference implementation for developers and device manufacturers.
This also implies that there are certain configurations and settings that cannot
be done in OP-TEE reference code. In short, there are cases when the default
configuration hasn't enabled all necessary security features for the end
product. There are a couple of reasons for that.

- Chipmakers and Semiconductors might only share specifications telling how to
  securely configure their devices with partners who have signed an NDA with
  them.
- In some cases a setting might be perfectly fine when OP-TEE is used in one
  particular environment, but the same setting might be insecure in another
  environment.

Because of this we always urge companies and device manufacturers making the end
product to follow the security guidelines from the chipmaker they are basing
their products on. Refer also to :ref:`platform_documentation`

.. _vendor_platform_code:

Vendor platform code
====================
A port of OP-TEE to a new SoC or board can contain code and configuration
provided by the vendor. Security critical configuration is spread across several
components, for example TF-A, U-Boot, OP-TEE, the device tree and fuses.

OP-TEE has a ``CFG_INSECURE`` switch (formerly ``CFG_WARN_INSECURE``). It
defaults to ``y``. When it is enabled, OP-TEE permits insecure development
configurations and prints the following at boot:

.. code-block:: none

    WARNING: This OP-TEE configuration might be insecure!

With ``CFG_INSECURE=y``, OP-TEE provides insecure defaults for functions that a
product platform must implement:

- ``tee_otp_get_hw_unique_key()`` returns an all-zero HUK (see
  :ref:`hardware_unique_key`).
- ``plat_init_soft_prng()`` seeds the software PRNG with a predictable value
  (see :ref:`porting_rng`).
- The REE file system runs without a monotonic counter when the platform does
  not implement one (see :ref:`porting_secure_storage`).

With ``CFG_INSECURE=n`` these defaults are not available, so a missing platform
implementation results in a build or runtime failure instead. Platforms can
also use ``CFG_INSECURE`` to gate their own security checks, for example checks
of the memory firewall configuration.

A device that boots and passes ``xtest`` can still have security features
disabled. The following sections describe the security relevant parts of a port.

Memory firewalls / TZASC
========================
Arm have defined a system IP / SoC peripheral called TrustZone Address Space
Controller (TZASC), for example the TZC-380 and the TZC-400, described in the
Arm Technical Reference Manuals with document numbers DDI 0431 and DDI 0504.
TZASC can be used to configure DDR memory into separate regions in the physical
address space, where each region can have an individual security level setting.
After enabling TZASC, it will perform security checks on transactions to memory
or peripherals. It is not always the case that TZASC is on a device, in some
cases the SoC has developed something equivalent. In OP-TEE this is very well
reflected, i.e., different platforms have different ways of protecting their
memory. On ARMv8-A platforms we are in most of the cases using Trusted Firmware
A as the boot firmware and there the secure bootloader is the one that
configures secure vs non-secure memory using TZASC. The takeaway here is that
you must make sure that you have configured whatever
memory firewall your device has such that it has a secure and a non-secure
memory area.

.. _memory_aliases:

Memory aliases and TZASC region 0
=================================
Some memory controllers ignore upper address bits, so two different physical
addresses can resolve to the same memory location (a memory alias). TZASC is not
memory alias aware: it can see two different addresses while the DDR controller
maps both to one location. If the second address falls through to an open
region, the isolation check is bypassed.

Region 0 of TZASC is special. It is the background region that covers the
whole address space and applies to any address that is not covered by another
region. On the TZC-380 it is configured as secure access only at reset, unless
firmware that runs earlier changes it. If a component (for example U-Boot or
TF-A) reconfigures region 0 to allow non-secure access, aliased addresses can
fall through to it and expose secure memory. The i.MX 8M is an example of
this combination: its DDR controller allows memory alias access, and a boot
loader that opens region 0 for non-secure access exposes OP-TEE memory through
the aliases.

The firmware that runs before OP-TEE configures region 0. On i.MX platforms,
OP-TEE can check at boot that region 0 is secure access only and panic if it is
not (``CFG_TZASC_REGION0_SECURE``). Whether the SoC has memory aliasing can be
tested by mapping high address bits of a known secure address from the normal
world and comparing the contents.

With ``CONFIG_STRICT_DEVMEM=y``, Linux blocks ``/dev/mem`` access to pages that
it considers RAM before the access reaches the bus. A denied access through
``/dev/mem`` therefore does not by itself demonstrate that the TZASC protects the
secure memory.

.. _non_cpu_bus_masters:

Non-CPU bus masters
===================
A memory firewall such as TZASC filters transactions from the CPU and some bus
masters. DMA engines, display controllers, video decoders, GPUs, Cortex-M cores
and other non-CPU masters can have their own secure/non-secure attributes
configured in the SoC interconnect. If these attributes are not configured,
such a master can read or write secure DRAM even when TZASC is configured
correctly. An SMMU/IOMMU that is not configured, or that is bypassed, does not
restrict DMA to the secure regions.

The relevant checks are:

- The secure/non-secure attribute of each master in the SoC interconnect or bus
  firewall.
- The SMMU/IOMMU configuration, or an equivalent way to block DMA to the secure
  regions.
- Whether a DMA-capable peripheral can read a known secure buffer from the
  normal world.

.. _secure_peripherals:

Secure peripheral ownership
===========================
Peripherals that are used by the secure world, such as crypto accelerators, the
TRNG, fuse controllers and secure timers, can be accessed by the normal world if
they are mapped as non-secure. Linux drivers for the same peripherals can then
read or write them and interfere with the OP-TEE drivers that use the same
hardware.

OP-TEE configures its interrupts as Group 0 on GICv2 and as Secure Group 1 on
GICv3 and GICv4. If an interrupt that the secure
world uses is configured as Non-secure Group 1, the normal world can handle or
mask it.

The ownership of each peripheral is defined by the SoC bus firewall. OP-TEE
contains drivers for some of these firewalls. Device tree nodes and Linux drivers for
peripherals that belong to the secure world can be removed so that the two
worlds do not access the same device. The secure interrupt configuration
determines whether secure interrupts can be handled or masked by the non-secure
side.

.. _hardware_unique_key:

Hardware Unique Key
===================
Most devices have some kind of Hardware Unique Key (HUK) that is mainly used to
derive other keys. The HUK could for example be used when deriving keys used in
secure storage etc. The important thing with the HUK is that it needs to be well
protected and in the best case the HUK should never ever be readable directly
from software, not even from the secure side. There are different solutions to
this, crypto accelerator might have support for it or, it could involve another
secure co-processor.

In OP-TEE the HUK **is** just **stubbed**. The default implementation of
``tee_otp_get_hw_unique_key()`` returns all zeroes and is only available with
``CFG_INSECURE=y``, so a build with ``CFG_INSECURE=n`` fails to link unless the
platform provides its own implementation. In a real secure product you **must**
replace this with something else. If your device lacks the hardware support for
a HUK, then you must at least change this to something else than just zeroes.
But, remember it is not good secure practice to store a key in software,
especially not the key that is the root for everything else, so this is not
something we recommend that you should do.

The HUK must be unique per device and secret. If the HUK is derived from a value
that is readable by the normal world, for example a chip ID, an SoC serial
number or a MAC address, possibly combined with a fixed salt, then the value is
not secret and every device that shares the same input has the same HUK. If the
HUK is read from fuses or OTP regions that are also mapped as non-secure, it is
readable from the normal world. OP-TEE derives the secure storage key (SSK),
the TA unique key, the default TA encryption key, the die ID and the RPMB key
from the HUK, so a HUK that is known or shared compromises
those secrets on all devices that share it.

The platform implementation of ``tee_otp_get_hw_unique_key()`` must:

- Return a per-device secret that is not readable outside the secure world, for
  example a key protected by a crypto accelerator or a secure-only OTP/eFuse
  region.
- Return the same value on every boot. Keys derived from the HUK, such as the
  SSK and the RPMB key, change if the HUK changes, and data that was protected
  with the previous keys can no longer be accessed.
- Not fall back to a fixed or all-zero key in a production build.

.. _core_pub_priv_keypair:

Trusted Application private/public keypair
==========================================
By default all Trusted Applications (TA's) are signed with the pre-generated
RSA development key (private key). This key is located in the ``keys``
folder (in the root of optee_os.git) and is named ``default_ta.pem``. This key
**must** be replaced with your own key and you should **never ever** check-in
this private key in the source code tree when in use in a real product. The
recommended way to store private keys is to use some kind of HSM_ (Hardware
Security Module), but an alternative would be temporary put the private key on a
computer considered as secure when you are about to sign TA's intended to be
used in real products. Typically it is only a few number of people having access
to this type of key in company.

The signing key is selected with ``TA_SIGN_KEY`` (default
``keys/default_ta.pem``). ``TA_PUBLIC_KEY`` (default ``TA_SIGN_KEY``) selects the
public key that is embedded in OP-TEE. When TAs are signed with an external
HSM, ``TA_SIGN_KEY`` can be set to a dummy key and ``TA_PUBLIC_KEY`` to the
public key of the HSM. TAs can also be verified with subkeys, see
:ref:`subkeys`.

.. _porting_ta_enc_key:

Trusted Application encryption key
==================================
With ``CFG_ENCRYPT_TA=y``, REE file system TAs are encrypted with
``TA_ENC_KEY`` at build time (see :ref:`ree_fs_ta`). At runtime OP-TEE gets the
decryption key from ``tee_otp_get_ta_enc_key()``. The default implementation
derives a device specific key from the HUK. A TA can be encrypted with a device
specific or a class wide key, and the default implementation only supports the
device specific one.

The default ``TA_ENC_KEY`` is a dummy key that matches the all-zero default HUK.
A product that uses TA encryption provides its own key and key handling.

.. _porting_rng:

Random Number Generator
=======================
By default OP-TEE is configured with a software PRNG. The entropy is added to
software PRNG at various places, but unfortunately it is still quite easy to
predict the data added as entropy. As a consequence, unless the RNG is based on
hardware the generated random will be quite weak.

If your platform has a hardware entropy source, you should set
``CFG_WITH_SOFTWARE_PRNG`` to ``n``, and provide an implementation for
``hw_get_random_bytes()``, which returns multiple bytes of entropy.

When ``CFG_WITH_SOFTWARE_PRNG=n``, the platform can enable a PTA service for
normal world to retrieve good quality random bytes. See configuration
switches ``CFG_HWRNG_PTA`` and ``CFG_HWRNG_QUALITY``, from 0 to 1024.

When ``CFG_WITH_SOFTWARE_PRNG=n``, the random number generator is made
available to OP-TEE drivers and frameworks, including Trusted Applications
(through GP TEE Internal Core API) and normal world (when ``CFG_HWRNG_PTA=y``).

When ``CFG_WITH_SOFTWARE_PRNG=y`` (the default), the software PRNG is seeded by
``plat_init_soft_prng()``. The default implementation uses a predictable seed
and is only available with ``CFG_INSECURE=y``. A platform with a hardware
entropy source can instead override ``plat_init_soft_prng()`` and seed the
software PRNG from it with ``crypto_rng_init()``.

A platform that has a TRNG, but where the driver for it is not enabled, uses
the software PRNG with whichever seed ``plat_init_soft_prng()`` provides. This
is also the case when the TRNG is part of a crypto accelerator whose driver is
disabled.

If the same TRNG is shared with the normal world without arbitration, the normal
world can access the TRNG while the secure world uses it. TRNG output can be
validated with a statistical test suite such as the NIST suite.

.. _porting_secure_storage:

Secure storage and rollback protection
======================================
OP-TEE can store Trusted Application data either in the normal world file
system (``CFG_REE_FS=y``, the default) or in the Replay Protected Memory Block
(RPMB) partition of an eMMC device (``CFG_RPMB_FS=y``, default ``n``). The REE
file system encrypts and integrity protects the blobs. On its own it does not
protect against rollback: an attacker with write access to the normal world file
system can restore an old snapshot of the storage, and OP-TEE then sees old
counters, old credentials and old anti-rollback state.

Rollback protection of the REE file system requires one of:

- ``CFG_REE_FS_INTEGRITY_RPMB=y`` (the default when ``CFG_RPMB_FS=y``), which
  stores the root hash of the REE file system in RPMB.
- A platform implementation of ``nv_counter_get_ree_fs()`` and
  ``nv_counter_incr_ree_fs_to()``, backed by a hardware monotonic counter, used
  when ``CFG_REE_FS_INTEGRITY_RPMB=n``. Without it, OP-TEE prints a warning and
  continues without rollback protection when ``CFG_INSECURE=y``, and fails to
  open the REE file system when ``CFG_INSECURE=n``.

The RPMB key is derived from the HUK and the eMMC CID (see
:ref:`hardware_unique_key`). ``tee-supplicant`` can emulate an RPMB device,
which its default build enables. The emulated device is kept in the memory of
the ``tee-supplicant`` process, so its contents, key and write counter are lost
when ``tee-supplicant`` restarts, and it does not exercise the real eMMC
behavior. ``CFG_RPMB_FS_DEV_ID`` selects which MMC device is used, and the
device numbering can differ between the boot loader and the kernel.

See :ref:`secure_storage` for the details of both implementations.

.. _porting_rpmb_provisioning:

RPMB key provisioning
=====================
The RPMB key is programmed once and cannot be changed afterwards.

- ``CFG_RPMB_TESTKEY=y`` uses a hard coded key from the OP-TEE source code.
  The key is publicly known and identical on all devices.
- With ``CFG_RPMB_TESTKEY=n`` (the default) the key is derived from the HUK and
  the eMMC CID. The CID is readable from the normal world, so anyone who knows
  the HUK can compute the RPMB key.
- ``CFG_RPMB_WRITE_KEY=y`` lets OP-TEE program the key into an eMMC device that
  has no key yet. The key programming request travels through the normal world
  to the eMMC device, so the key is exposed to the normal world. The OP-TEE
  build configuration states that this option must not be enabled in product
  builds.
- With ``CFG_RPMB_WRITE_KEY=y``, OP-TEE programs the key into any eMMC device
  without a key that it is pointed to. ``CFG_RPMB_WRITE_KEY_CID`` restricts
  provisioning to the device with the given CID, and the platform function
  ``plat_rpmb_key_is_ready()`` can prevent provisioning until the platform is
  ready.
- ``CFG_RPMB_FS_DEV_ID`` selects which MMC device is used, and the
  ``tee-supplicant`` option ``--rpmb-cid`` selects the RPMB device by its CID. If
  the key is programmed while the HUK is still a development value, the key
  derived later from the production HUK does not match and RPMB accesses fail.

See :ref:`rpmb` for the full description.

Secure Clock
============
The Time API in GlobalPlatform Internal Core API specification defines three
sources of time; system time, TA persistent time and REE time. The REE time is
by nature considered as an unsecure source of time, but the other two should in
a fully trustable hardware make use of trustable source of time, i.e., a secure
clock. Note that from GlobalPlatform point of view it is not required to make
use of a secure clock, i.e., it is OK to use time from REE, but the level of
trust should be reflected by the ``gpd.tee.systemTime.protectionLevel`` property
and the ``gpd.tee.TAPersistentTime.protectionLevel`` property (100=REE
controlled clock, 1000=TEE controlled clock).

The system time source is selected with a ``CFG_SECURE_TIME_SOURCE_*`` option,
for example ``CFG_SECURE_TIME_SOURCE_CNTPCT`` for the Arm generic timer or
``CFG_SECURE_TIME_SOURCE_REE`` for time from the normal world. Each time source
reports its own protection level, so a platform that adds a secure time source
also reports the matching protection level.

Root and Chain of Trust
=======================
To be able to assure that your devices are running the (untampered) binaries you
intended to run you will need to establish some kind of trust anchor on the
devices.

The most common way of doing that is to put the root public key in some read
only memory on the device. Quite often SoC's/OEM's stores public key(s) directly
or the hash(es) of the public key(s) in OTP_. When the boot ROM (which indeed
needs to be ROM) is about to load the first stage bootloader it typically reads
the public key from the software binary itself, hash the key and compare it to
the key in OTP_. If they are matching, then the boot ROM can be sure that the
first stage bootloader was indeed signed with the corresponding private key.

In OP-TEE you will not find any code at all related to this and this is a good
example when it is hard for us to do this in a generic way since device
manufacturers all tend to do this in their own unique way and they are not very
keen on sharing their low level boot details and security implementation with
the rest of the world. This is especially true on ARMv7-A. For ARMv8-A it looks
a bit better, since Arm in Trusted Firmware A have implemented and defined how
to abstract the chain of trust (see auth-framework.rst_).
We have successfully verified OP-TEE by using the authentication framework from
Trusted Firmware A (see :ref:`secure_boot` for the details).

Anti-rollback protection is part of a chain of trust. Without rollback
counters, an attacker who can write the boot medium can flash an old,
known-vulnerable OP-TEE or TF-A image that is still correctly signed. The
counters can be stored in RPMB or in fuses, and each boot stage can check and
update them. If secure boot is enabled in software but the corresponding fuse is
left open, or if the images are signed with a debug key instead of the
production key, the chain of trust does not hold. The chain of trust covers
every stage from the boot ROM through TF-A and OP-TEE to the TAs, and each stage
verifies the next one.

.. _porting_power_transitions:

Power transitions and secondary cores
=====================================
A TZASC or bus firewall that is not in an always-on power domain loses its
configuration on suspend-to-RAM, and must be reconfigured on resume. For
example, the TZASC is not part of an always-on power domain on i.MX 8M.
Per-core secure configuration
must also be applied when secondary cores are brought up. Secure SRAM/OCRAM that
holds stacks or keys can be left readable across low-power states if it is not
cleared or protected. These paths are not covered by a cold boot test.

.. _ree_tee_interface:

REE/TEE interface
=================
The SMC/PTA interface between the normal world and OP-TEE is part of the attack
surface. A bug in a platform specific handler can let a normal world process
reach an operation that is otherwise privileged. The parts of the interface to
check are:

- The validation of parameters of platform specific SMC handlers in TF-A and
  OP-TEE, such as addresses, sizes, identifiers and parameter types, which are
  inputs from the normal world.
- The check of shared memory buffers against the secure and non-secure memory
  maps (``core_pbuf_is()``). Without such a check the normal world can point
  OP-TEE at secure memory.
- Cache maintenance and coherency on shared buffers, which affects whether
  OP-TEE reads stale data or returns corrupted data.
- Vendor added SMC and PTA services that expose operations to the normal world.
  Each service that reaches a privileged operation is reachable by any process
  that can issue the call.
- Fuzzing of the interface.

.. _debug_interfaces:

Debug interfaces
================
The following debug features affect the secure world:

- JTAG/SWD access to the secure world, including CoreSight/ETM trace, can be
  controlled with fuses or an authenticated debug unlock mechanism.
- A secure UART console prints TEE logs, assertions and panic information. The
  amount of output is controlled by ``CFG_TEE_CORE_LOG_LEVEL`` and
  ``CFG_TEE_CORE_DEBUG`` (see :ref:`porting_production_build`).

An authenticated debug unlock mechanism provides field debugging without
leaving the interface permanently open.

.. _porting_production_build:

Production build configuration
==============================
The default OP-TEE configuration is a development configuration. The following
options affect security and have defaults or common development settings that
differ from a production configuration:

- ``CFG_INSECURE`` defaults to ``y``. With ``CFG_INSECURE=n`` the insecure
  defaults are not available and platform security checks can be enabled (see
  :ref:`vendor_platform_code`).
- ``CFG_TEE_CORE_DEBUG`` enables assertions and lock checks, more verbose panic
  and assert messages, and stack dumps on aborts.
- ``CFG_TEE_CORE_LOG_LEVEL`` defines which core messages are printed on the
  secure console. Level ``0`` also disables TA logs.
- ``DEBUG=1`` disables compiler optimization and enables debug information.
- ``CFG_UNWIND`` prints call stacks. Since the unwinding of TA code is done in
  the privileged layer, it weakens the user/kernel isolation, and the build
  configuration states that it should be disabled in release builds.
- ``CFG_RPMB_TESTKEY`` and ``CFG_RPMB_WRITE_KEY`` affect the secrecy of the
  RPMB key (see :ref:`porting_rpmb_provisioning`).

OP-TEE also has configurable exploit mitigations, such as ASLR for the core and
for TAs, stack canaries, Spectre workarounds, non-executable data, Branch
Target Identification, Pointer Authentication, Memory Tagging and Privileged
Access Never. Some of them are disabled by default, and some depend on CPU
features and toolchain support.

``mk/config.mk`` and ``core/arch/<arch>/<arch>.mk`` document each option and its
default.

A production configuration can be kept separately and compared with the
development configuration, for example in CI.

.. _porting_checklist:

Security porting checklist
==========================
The following checklist summarizes the topics in :ref:`porting_production`.

- Insecure defaults: no platform function relies on a default that is only
  available with ``CFG_INSECURE=y``.
- Memory: TZASC/firewalls configured and locked, including memory aliases
  (region 0) and non-CPU bus masters.
- Peripherals: secure-only peripherals and secure interrupts not reachable from
  the normal world.
- HUK: unique per device and secret, not derived from a world-readable value.
- TA keys: ``default_ta.pem`` replaced by a product key, and with
  ``CFG_ENCRYPT_TA=y`` a product ``TA_ENC_KEY`` and matching
  ``tee_otp_get_ta_enc_key()``.
- RNG: hardware TRNG driver ported, enabled, validated and secure-only.
- Secure storage: rollback protection through RPMB
  (``CFG_REE_FS_INTEGRITY_RPMB`` or ``CFG_RPMB_FS``) or a platform monotonic
  counter, with the RPMB key derived from a unique HUK, verified on real
  hardware.
- Secure boot: full chain of trust with production keys and anti-rollback
  counters.
- Power: security configuration restored after suspend/resume and on secondary
  cores.
- Interface: platform SMC/PTA services reviewed and parameter checks in place.
- Debug: JTAG/SWD, trace and secure console locked down in production.
- Build: production configuration without development flags, with
  ``CFG_INSECURE=n`` and the exploit mitigations supported by the CPU.
- Process: production and development configurations compared, and negative
  tests from the normal world (``/dev/mem``, DMA, fuse reads) run.


.. _core/arch/arm/plat-hikey/conf.mk: https://github.com/OP-TEE/optee_os/blob/master/core/arch/arm/plat-hikey/conf.mk


.. _auth-framework.rst: https://trustedfirmware-a.readthedocs.io/en/latest/design/auth-framework.html
.. _HSM: https://en.wikipedia.org/wiki/Hardware_security_module
.. _MAINTAINERS: https://github.com/OP-TEE/optee_os/blob/master/MAINTAINERS
.. _OTP: https://en.wikipedia.org/wiki/Programmable_read-only_memory
