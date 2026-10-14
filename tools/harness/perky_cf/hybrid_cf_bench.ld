ENTRY(bench_init)
SECTIONS { . = 0x40000400; .text : { *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) } . = ALIGN(4); .bss (NOLOAD) : { __bss_start = .; *(.bss*) *(COMMON) __bss_end = .; } /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) } }
