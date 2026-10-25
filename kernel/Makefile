# Out-of-tree build. CachyOS kernels are built with clang: default to LLVM=1.
KVER ?= $(shell uname -r)
KDIR ?= /lib/modules/$(KVER)/build
LLVM ?= 1

obj-m += lenovo_fanboost.o

all:
	$(MAKE) -C $(KDIR) LLVM=$(LLVM) M=$(CURDIR) modules

clean:
	$(MAKE) -C $(KDIR) LLVM=$(LLVM) M=$(CURDIR) clean

.PHONY: all clean
