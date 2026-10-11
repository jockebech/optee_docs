.. _porting_guidelines:

##################
Porting guidelines
##################
This document serves a dual purpose:

* Serve as a base for getting OP-TEE up and running on a new device with initial
  xtest validation passing. This is the first part of this document.

* Highlight the missing pieces if you intend to make a real secure product, that
  is what the second part of this document is about.

We are trying our best to implement full end to end security in OP-TEE in a
generic way, but due to the nature of devices being different, NDA etc, it is
not always possible for us to do so and in those cases, we most often try to
write a generic API, but we will just stub the code. This porting guideline
highlights the missing pieces that must be addressed in a real secure consumer
device. Hopefully we will sooner or later get access to devices where we at
least can make reference implementations publicly available to everyone for the
missing pieces we are talking about here.

.. _add_a_new_platform:

Add a new platform
******************
The first thing you need to do after you have decided to port OP-TEE to another
device is to add a new platform device. That can either be adding a new platform
variant (``PLATFORM_FLAVOR``) if it is a device from a family already supported,
or it can be a brand new platform family (``PLATFORM``). Typically this initial
setup involve configuring UART, memory addresses etc. For simplicity let us call
our fictive platform for "gendev" just so we have something to refer to when
writing examples further down.

core/arch/arm
=================
In ``core/arch/arm`` you will find all the currently supported devices. That is
where you are supposed to add a new platform or modify an existing one.
Typically you will find this set of files in a specific platform folder:

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
for the platform, the core configurations (architecture and number of cores),
the main configuration directives (generic boot, arm trusted firmware support,
generic time source, console driver, etc...) and some platform default
configuration settings.

.. code-block:: make

    PLATFORM_FLAVOR ?= hikey
    
    include core/arch/arm/cpu/cortex-armv8-0.mk
    
    $(call force,CFG_TEE_CORE_NB_CORE,8)
    $(call force,CFG_GENERIC_BOOT,y)
    $(call force,CFG_PL011,y)
    $(call force,CFG_PM_STUBS,y)
    $(call force,CFG_SECURE_TIME_SOURCE_CNTPCT,y)
    $(call force,CFG_WITH_ARM_TRUSTED_FW,y)
    $(call force,CFG_WITH_LPAE,y)
    
    ta-targets = ta_arm32
    ta-targets += ta_arm64
    
    CFG_NUM_THREADS ?= 8
    CFG_CRYPTO_WITH_CE ?= y
    CFG_WITH_STACK_CANARIES ?= y
    CFG_CONSOLE_UART ?= 3
    CFG_DRAM_SIZE_GB ?= 2

**main.c**

This platform specific file will contain power management handlers and code
related to the UART. We will talk more about the information related to the
handlers further down in this document. For our gendev device it could look like
this (here we are excluding the necessary license header to save some space):

.. code-block:: c

    #include <console.h>
    #include <drivers/serial8250_uart.h>
    #include <kernel/generic_boot.h>
    #include <kernel/panic.h>
    #include <kernel/pm_stubs.h>
    #include <mm/core_mmu.h>
    #include <platform_config.h>
    #include <stdint.h>
    #include <tee/entry_fast.h>
    #include <tee/entry_std.h>
    
    static void main_fiq(void)
    {
    	panic();
    }
    
    static const struct thread_handlers handlers = {
    	.std_smc = tee_entry_std,
    	.fast_smc = tee_entry_fast,
    	.nintr = main_fiq,
    	.cpu_on = cpu_on_handler,
    	.cpu_off = pm_do_nothing,
    	.cpu_suspend = pm_do_nothing,
    	.cpu_resume = pm_do_nothing,
    	.system_off = pm_do_nothing,
    	.system_reset = pm_do_nothing,
    };
    
    const struct thread_handlers *generic_boot_get_handlers(void)
    {
    	return &handlers;
    }
    
    /*
     * Register the physical memory area for peripherals etc. Here we are
     * registering the UART console.
     */
    register_phys_mem(MEM_AREA_IO_NSEC, CONSOLE_UART_BASE, SERIAL8250_UART_REG_SIZE);
    
    static struct serial8250_uart_data console_data;
    
    void console_init(void)
    {
    	serial8250_uart_init(&console_data, CONSOLE_UART_BASE,
    			     CONSOLE_UART_CLK_IN_HZ, CONSOLE_BAUDRATE);
    	register_serial_console(&console_data.chip);
    }

**platform_config.h**

This is a mandatory header file for every platform, since there are several
files relying upon the existence of this particular file. This file is where
you will find the major differences between different platforms, since this is
where you do the memory configuration, define base addresses etc. we are going
to list a few here, but it probably makes more sense to have a look at the
already existing ``platform_config.h`` files for the other platforms. Our
fictive gendev could look like this:

.. code-block:: c

    #ifndef PLATFORM_CONFIG_H
    #define PLATFORM_CONFIG_H
    
    /* Make stacks aligned to data cache line length */
    #define STACK_ALIGNMENT		64
    
    /* 8250 UART */
    #define CONSOLE_UART_BASE	0xcafebabe /* UART0 */
    #define CONSOLE_BAUDRATE	115200
    #define CONSOLE_UART_CLK_IN_HZ	19200000
    
    /* Optional: when used with CFG_WITH_PAGER, defines the device SRAM */
    #define TZSRAM_BASE		0x3F000000
    #define TZSRAM_SIZE		(200 * 1024)
    
    /* Mandatory main secure RAM usually DDR */
    #define TZDRAM_BASE		0x60000000
    #define TZDRAM_SIZE		(32 * 1024 * 1024)
    
    /* Mandatory TEE RAM location and core load address */
    #define TEE_RAM_START		TZDRAM_BASE
    #define TEE_RAM_PH_SIZE		TEE_RAM_VA_SIZE
    #define TEE_RAM_VA_SIZE		(4 * 1024 * 1024)
    #define TEE_LOAD_ADDR		(TZDRAM_BASE + 0x20000)
    
    /* Mandatory TA RAM (external less secure RAM) */
    #define TA_RAM_START		(TZDRAM_BASE + TEE_RAM_VA_SIZE)
    #define TA_RAM_SIZE		(TZDRAM_SIZE - TEE_RAM_VA_SIZE)
    
    /* Mandatory: for static SHM, need a hardcoded physical address */
    #define TEE_SHMEM_START		0x08000000
    #define TEE_SHMEM_SIZE		(4 * 1024 * 1024)
    
    #endif /* PLATFORM_CONFIG_H */

This is minimal amount of information in the ``platform_config.h`` file. I.e,
the memory layout for on-chip and external RAM. Note that parts of the DDR
typically will need to be shared with normal world, so there is need for some
kind of memory firewall for this (more about that further down). As you can see
we have also added the UART configuration here, i.e., the ``DEVICE0_xyz`` part.

Binaries
========
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
also update the MAINTAINERS.md_ file accordingly. By being a maintainer for a
device you are responsible to keep it up to date and you will be asked every
quarter as part of the OP-TEE release schedule to test your device running the
latest OP-TEE software.

**Update build.git and manifest.git**

This isn't strictly necessary, but we are trying to create and maintain OP-TEE
developer builds that should make it easy to setup, build and deploy OP-TEE on
various devices. We encourage all maintainers to do the same for the boards they
are in charge of. Therefore please consider creating a new :ref:`manifest` (and
a new ``*.mk`` in :ref:`build`) for the device you have added to OP-TEE.

.. _vendor_platform_code:

Vendor platform code
********************
A port of OP-TEE to a new SoC or board can contain code and configuration
provided by the vendor. Security critical configuration is spread across several
components, for example TF-A, U-Boot, OP-TEE, the device tree and fuses.

OP-TEE has a ``CFG_INSECURE`` switch (formerly ``CFG_WARN_INSECURE``, which is
deprecated). It defaults to ``y`` in ``mk/config.mk``. When it is enabled,
OP-TEE permits insecure development configurations and prints the following at
boot (info level):

.. code-block:: none

    WARNING: This OP-TEE configuration might be insecure!

``CFG_INSECURE=y`` has the following effects in the core:

- The weak default ``tee_otp_get_hw_unique_key()``, which returns an all-zero
  HUK, is only built when ``CFG_INSECURE=y`` (see :ref:`hardware_unique_key`).
- The weak default ``plat_init_soft_prng()``, which seeds the software PRNG from
  the system time, is only built when ``CFG_INSECURE=y`` (see
  :ref:`porting_rng`).
- With ``CFG_REE_FS_INTEGRITY_RPMB=n``, the REE file system continues without
  a monotonic counter when the platform does not implement
  ``nv_counter_get_ree_fs()`` (see :ref:`porting_secure_storage`).

Several platforms also use it to gate security checks. For example, on i.MX
``CFG_INSECURE=n`` forces ``CFG_TZASC_CHECK_ENABLED=y`` (i.MX 6 and i.MX 8M) and
``CFG_TZASC_REGION0_SECURE=y`` (i.MX 8M), and on STM32MP platforms it controls
whether firewall configuration errors cause a panic.

A device that boots and passes ``xtest`` can still have security features
disabled. The following sections describe the security relevant parts of a port.

.. _hardware_unique_key:

Hardware Unique Key
*******************
Most devices have some kind of Hardware Unique Key (HUK) that is mainly used to
derive other keys. The HUK could for example be used when deriving keys used in
secure storage etc. The important thing with the HUK is that it needs to be well
protected and in the best case the HUK should never ever be readable directly
from software, not even from the secure side. There are different solutions to
this, crypto accelerator might have support for it or, it could involve another
secure co-processor.

In OP-TEE the HUK **is** just **stubbed**. The function
``tee_otp_get_hw_unique_key(...)`` is declared in
`core/include/kernel/tee_common_otp.h`_ and the weak default implementation in
``core/kernel/otp_stubs.c`` returns all zeroes. That default is only built when
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
readable from the normal world. ``huk_subkey_derive()`` derives the secure
storage key (SSK), the TA unique key, the default TA encryption key, the die ID
and the RPMB key from the HUK, so a HUK that is known or shared compromises
those secrets on all devices that share it.

The platform implementation of ``tee_otp_get_hw_unique_key()`` must:

- Return a per-device secret that is not readable outside the secure world, for
  example a key protected by a crypto accelerator or a secure-only OTP/eFuse
  region.
- Return the same value on every boot. Keys derived from the HUK, such as the
  SSK and the RPMB key, change if the HUK changes, and data that was protected
  with the previous keys can no longer be accessed.
- Not fall back to a fixed or all-zero key in a production build.

.. _porting_secure_storage:

Secure storage and rollback protection
**************************************
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
  when ``CFG_REE_FS_INTEGRITY_RPMB=n``. The weak defaults return
  ``TEE_ERROR_NOT_IMPLEMENTED``. With ``CFG_INSECURE=y`` OP-TEE then prints
  ``WARNING (insecure configuration): Failed to get monotonic counter for REE
  FS, using 0`` and continues without rollback protection. With
  ``CFG_INSECURE=n`` opening the REE file system fails.

The RPMB key is derived from the HUK and the eMMC CID (see
:ref:`hardware_unique_key`). ``tee-supplicant`` is built with ``RPMB_EMU=1`` by
default. The emulated RPMB device is kept in the memory of the
``tee-supplicant`` process, so its contents, key and write counter are lost
when ``tee-supplicant`` restarts, and it does not exercise the real eMMC
behavior. ``CFG_RPMB_FS_DEV_ID`` selects which MMC device is used (on Linux
``tee-supplicant`` opens ``/dev/mmcblk<id>rpmb``), and the device numbering can
differ between the boot loader and the kernel.

See :ref:`secure_storage` for the details of both implementations.

.. _porting_rpmb_provisioning:

RPMB key provisioning
*********************
The RPMB key is programmed once and cannot be changed afterwards.

- ``CFG_RPMB_TESTKEY=y`` uses a hard coded key from ``core/tee/tee_rpmb_fs.c``.
  The key is publicly known and identical on all devices.
- With ``CFG_RPMB_TESTKEY=n`` (the default) the key is derived with
  ``huk_subkey_derive()`` from the HUK and the eMMC CID. The CID is readable
  from the normal world, so anyone who knows the HUK can compute the RPMB key.
- ``CFG_RPMB_WRITE_KEY=y`` (default ``n``) lets OP-TEE program the key into an
  eMMC device that has no key yet. The key programming request travels through
  the normal world (``tee-supplicant`` or the kernel) to the eMMC device, so the
  key is exposed to the normal world. ``mk/config.mk`` states that this option
  must not be enabled in product builds.
- With ``CFG_RPMB_WRITE_KEY=y``, OP-TEE programs the key into any eMMC device
  without a key that it is pointed to. ``CFG_RPMB_WRITE_KEY_CID`` restricts
  provisioning to the device with the given CID.
- ``plat_rpmb_key_is_ready()`` is checked before OP-TEE programs the key. The
  weak default returns ``true``.
- ``CFG_RPMB_FS_DEV_ID`` selects which MMC device is used, and the
  ``tee-supplicant`` option ``--rpmb-cid`` selects the RPMB device by its CID. If
  the key is programmed while the HUK is still a development value, the key
  derived later from the production HUK does not match and RPMB accesses fail.

See :ref:`rpmb` for the full description.

Secure Clock
************
The Time API in GlobalPlatform Internal Core API specification defines three
sources of time; system time, TA persistent time and REE time. The REE time is
by nature considered as an unsecure source of time, but the other two should in
a fully trustable hardware make use of trustable source of time, i.e., a secure
clock. Note that from GlobalPlatform point of view it is not required to make
use of a secure clock, i.e., it is OK to use time from REE, but the level of
trust should be reflected by the ``gpd.tee.systemTime.protectionLevel`` property
and the ``gpd.tee.TAPersistentTime.protectionLevel`` property (100=REE
controlled clock, 1000=TEE controlled clock). So the functions that one needs to
pay attention to are ``tee_time_get_sys_time(...)`` and
``tee_time_get_ta_time(...)``. If your hardware has a secure clock, then you
probably want to change the implementation there to instead use the secure clock
(and then you would also need to update the property accordingly, i.e.,
``tee_time_get_sys_time_protection_level()`` and the variable
``ta_time_prot_lvl`` in ``tee_svc.c``).

Root and Chain of Trust
***********************
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

Hardware Crypto IP
******************
By default OP-TEE uses a software crypto library (currently mbed TLS and
LibTomCrypt) and you have the ability to enable Crypto Extensions that were
introduced with ARMv8-A (if the device is capable of that). Some of the devices
supported in OP-TEE OS repository have hardware crypto capabilities. A
framework, named drvcrypt has been designed to integrate them. The
``drvcrypt_register_*()`` API functions allow drivers to register support for
given cryptographic operations in OP-TEE core crypto API. Our
:ref:`cryptographic_implementation` page describes in detail how the Crypto API
is integrated.

.. _porting_rng:

Random Number Generator
***********************
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
``plat_init_soft_prng()``. The weak default seeds it with the system time, or
with zeroes when ``CFG_SECURE_TIME_SOURCE_REE=y``, and it is only built when
``CFG_INSECURE=y``. A platform with a hardware entropy source can instead
override ``plat_init_soft_prng()`` and seed the software PRNG from it with
``crypto_rng_init()``, as for example the STM32 RNG and SMCCC TRNG drivers do.

A platform that has a TRNG but where the TRNG driver is not enabled uses the
software PRNG with whichever seed ``plat_init_soft_prng()`` provides. For
example, on i.MX the CAAM RNG driver (``CFG_NXP_CAAM_RNG_DRV``, enabled with
``CFG_NXP_CAAM``) sets ``CFG_WITH_SOFTWARE_PRNG ?= n`` and provides
``hw_get_random_bytes()``, or seeds the software PRNG when
``CFG_WITH_SOFTWARE_PRNG=y``. With ``CFG_NXP_CAAM=n`` neither is done and the
software PRNG uses the default seed.

If the same TRNG is shared with the normal world without arbitration, the normal
world can access the TRNG while the secure world uses it. TRNG output can be
validated with a statistical test suite such as the NIST suite.

.. _porting_production_build:

Production build configuration
******************************
The default OP-TEE configuration is a development configuration. The following
options affect security and have defaults or common development settings that
differ from a production configuration:

- ``CFG_INSECURE`` defaults to ``y``. With ``CFG_INSECURE=n`` the insecure
  weak defaults are not built and several platform security checks are enabled
  (see :ref:`vendor_platform_code`).
- ``CFG_TEE_CORE_DEBUG`` defaults to ``y``. It enables assertions and lock
  checks, more verbose panic and assert messages, and stack dumps on data and
  prefetch aborts.
- ``CFG_TEE_CORE_LOG_LEVEL`` defaults to ``2`` (error and info). It defines
  which core messages are printed on the secure console. Level ``0`` also
  disables TA logs.
- ``DEBUG=1`` forces ``CFG_CC_OPT_LEVEL=0`` (no optimization) and
  ``CFG_DEBUG_INFO=y``.
- ``CFG_DEBUG_INFO`` defaults to ``y`` and embeds debug information in the core.
- ``CFG_UNWIND`` defaults to ``y`` when ``CFG_TEE_CORE_DEBUG=y`` and prints call
  stacks. ``mk/config.mk`` states that it weakens the user/kernel isolation,
  since the unwinding of TA code is done in the privileged layer, and that it
  should be disabled in release builds.
- ``CFG_RPMB_TESTKEY`` (default ``n``) uses a publicly known RPMB key (see
  :ref:`porting_rpmb_provisioning`).
- ``CFG_RPMB_WRITE_KEY`` (default ``n``) exposes the RPMB key to the normal
  world when the key is programmed.
- ``CFG_CORE_ASLR`` defaults to ``y``. ``CFG_CORE_WORKAROUND_SPECTRE_BP``,
  ``CFG_CORE_WORKAROUND_SPECTRE_BP_SEC`` and
  ``CFG_CORE_WORKAROUND_NSITR_CACHE_PRIME`` default to ``y`` on Arm.
- ``CFG_WITH_PAGER`` defaults to ``n`` and requires SRAM.

A production configuration can be kept separately and compared with the
development configuration, for example in CI.

Power Management / PSCI
***********************
In the :ref:`add_a_new_platform` section where we talked about the file
``main.c``, we added a couple of handlers related to power management, we are
talking about the following lines:

.. code-block:: c

    .cpu_on = cpu_on_handler,
    .cpu_off = pm_do_nothing,
    .cpu_suspend = pm_do_nothing,
    .cpu_resume = pm_do_nothing,
    .system_off = pm_do_nothing,
    .system_reset = pm_do_nothing,

The only function that actually does something there is the ``cpu_on`` function,
the rest of them are stubbed. The main reason for that is because we think that
how to suspend and resume is a device dependent thing. The code in OP-TEE is
prepared so that callbacks etc from Trusted Firmware A will be routed to OP-TEE,
but since the function(s) are just stubbed we will not do anything and just
return. In a real production device, you would probably want to save and restore
CPU states, secure hardware IPs' registers and TZASC and other memory firewall
related setting when these callbacks are being called.

A TZASC or bus firewall that is not in an always-on power domain loses its
configuration on suspend-to-RAM, and must be reconfigured on resume. For
example, on i.MX 8M the TZASC is not in an always-on power domain and OP-TEE
reconfigures it from a ``PM_OP_RESUME`` callback in
``core/arch/arm/plat-imx/tzc380.c``. Per-core secure configuration must also be
applied when secondary cores are brought up. Secure SRAM/OCRAM that holds stacks
or keys can be left readable across low-power states if it is not cleared or
protected. These paths are not covered by a cold boot test.

Memory firewalls / TZASC
************************
Arm have defined a system IP / SoC peripheral called TrustZone Address Space
Controller (TZASC, see TZC-380_ and TZC-400_). TZASC can be used to configure
DDR memory into separate regions in the physical address space, where each
region can have an individual security level setting. After enabling TZASC, it
will perform security checks on transactions to memory or peripherals. It is not
always the case that TZASC is on a device, in some cases the SoC has developed
something equivalent. In OP-TEE this is very well reflected, i.e., different
platforms have different ways of protecting their memory. On ARMv8-A platforms
we are in most of the cases using Trusted Firmware A as the boot firmware and
there the secure bootloader is the one that configures secure vs non-secure
memory using TZASC (see plat_arm_security_setup_ in TF-A). The takeaway here is
that you must make sure that you have configured whatever memory firewall your
device has such that it has a secure and a non-secure memory area.

.. _non_cpu_bus_masters:

Non-CPU bus masters
*******************
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

.. _memory_aliases:

Memory aliases and TZASC region 0
*********************************
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
this combination: its DDR controller allows memory alias access, and U-Boot
configures region 0 for secure and non-secure read/write access in
``enable_tzc380()`` (``arch/arm/mach-imx/imx8m/soc.c``) because some bus masters,
such as the USB dwc3 controllers, do not work with secure memory. TF-A commit
``fix(imx8m): don't reconfigure default region0`` removed the corresponding
region 0 configuration from TF-A.

The firmware that runs before OP-TEE configures region 0. On i.MX platforms with
a TZC-380, ``CFG_TZASC_REGION0_SECURE=y`` makes OP-TEE panic at boot with
``region0 is not secure configured, non-secure memory alias access possible!``
if region 0 is not secure access only. It is forced to ``y`` on i.MX 8M when
``CFG_INSECURE=n``. Whether the SoC has memory aliasing can be
tested by mapping high address bits of a known secure address from the normal
world and comparing the contents.

With ``CONFIG_STRICT_DEVMEM=y``, Linux blocks ``/dev/mem`` access to pages that
it considers RAM before the access reaches the bus. A denied access through
``/dev/mem`` therefore does not by itself demonstrate that the TZASC protects the
secure memory.

.. _secure_peripherals:

Secure peripheral ownership
***************************
Peripherals that are used by the secure world, such as crypto accelerators, the
TRNG, fuse controllers and secure timers, can be accessed by the normal world if
they are mapped as non-secure. Linux drivers for the same peripherals can then
read or write them and interfere with the OP-TEE drivers that use the same
hardware.

OP-TEE configures its interrupts as Group 0 on GICv2 and as Secure Group 1 on
GICv3 and GICv4 (see ``core/drivers/gic.c``). If an interrupt that the secure
world uses is configured as Non-secure Group 1, the normal world can handle or
mask it.

The ownership of each peripheral is defined by the SoC bus firewall. Examples
of firewall drivers in OP-TEE are the i.MX CSU driver (``CFG_IMX_CSU``) and the
STM32 ETZPC and RIFSC drivers (``CFG_STM32_ETZPC``, ``CFG_STM32_RIFSC``) in
``core/drivers/firewall``. Device tree nodes and Linux drivers for
peripherals that belong to the secure world can be removed so that the two
worlds do not access the same device. The secure interrupt configuration
determines whether secure interrupts can be handled or masked by the non-secure
side.

.. _core_pub_priv_keypair:

Trusted Application private/public keypair
******************************************
By default all Trusted Applications (TA's) are signed with the pre-generated
2048-bit RSA development key (private key). This key is located in the ``keys``
folder (in the root of optee_os.git) and is named ``default_ta.pem``. This key
**must** be replaced with your own key and you should **never ever** check-in
this private key in the source code tree when in use in a real product. The
recommended way to store private keys is to use some kind of HSM_ (Hardware
Security Module), but an alternative would be temporary put the private key on a
computer considered as secure when you are about to sign TA's intended to be
used in real products. Typically it is only a few number of people having access
to this type of key in company. The key handling in OP-TEE is currently a bit
limited since we only support a single key which is used for all TA's. We have
plans on extending this to make it a bit more flexible. Exactly when that will
happen has not been decided yet.

.. _debug_interfaces:

Debug interfaces
****************
The following debug features affect the secure world:

- JTAG/SWD access to the secure world, including CoreSight/ETM trace, can be
  controlled with fuses or an authenticated debug unlock mechanism.
- A secure UART console prints TEE logs, assertions and panic information. The
  amount of output is controlled by ``CFG_TEE_CORE_LOG_LEVEL`` and
  ``CFG_TEE_CORE_DEBUG`` (see :ref:`porting_production_build`).

An authenticated debug unlock mechanism provides field debugging without
leaving the interface permanently open.

.. _ree_tee_interface:

REE/TEE interface
*****************
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

.. _platform_ports:

Platform ports
**************
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

.. _porting_checklist:

Security porting checklist
**************************
The following checklist summarizes the topics in this document.

- HUK: unique per device and secret, not derived from a world-readable value.
- Memory: TZASC/firewalls configured and locked, including non-CPU bus masters
  and memory aliases (region 0).
- Peripherals: secure-only peripherals and secure interrupts not reachable from
  the normal world.
- Build: production configuration without development flags and with
  ``CFG_INSECURE=n``.
- Secure storage: rollback protection through RPMB
  (``CFG_REE_FS_INTEGRITY_RPMB`` or ``CFG_RPMB_FS``) or a platform monotonic
  counter, with the RPMB key derived from a unique HUK, verified on real
  hardware.
- RNG: hardware TRNG driver ported, enabled, validated and secure-only.
- Secure boot: full chain of trust with production keys and anti-rollback
  counters.
- Debug: JTAG/SWD, trace and secure console locked down in production.
- Interface: platform SMC/PTA services reviewed and parameter checks in place.
- Power: security configuration restored after suspend/resume and on secondary
  cores.
- Process: production and development configurations compared, and negative
  tests from the normal world (``/dev/mem``, DMA, fuse reads) run.


.. _core/arch/arm/plat-hikey/conf.mk: https://github.com/OP-TEE/optee_os/blob/master/core/arch/arm/plat-hikey/conf.mk
.. _core/include/crypto/crypto.h: https://github.com/OP-TEE/optee_os/blob/master/core/include/crypto/crypto.h
.. _core/include/kernel/tee_common_otp.h: https://github.com/OP-TEE/optee_os/blob/master/core/include/kernel/tee_common_otp.h


.. _auth-framework.rst: https://github.com/ARM-software/arm-trusted-firmware/blob/master/docs/design/auth-framework.rst
.. _HSM: https://en.wikipedia.org/wiki/Hardware_security_module
.. _MAINTAINERS.md: https://github.com/OP-TEE/optee_os/blob/master/MAINTAINERS
.. _OTP: https://en.wikipedia.org/wiki/Programmable_read-only_memory
.. _plat_arm_security_setup: https://github.com/ARM-software/arm-trusted-firmware/search?utf8=%E2%9C%93&q=plat_arm_security_setup&type=
.. _TZC-380: http://infocenter.arm.com/help/index.jsp?topic=/com.arm.doc.ddi0431c/index.html
.. _TZC-400: http://infocenter.arm.com/help/index.jsp?topic=/com.arm.doc.100325_0001_02_en/index.html
