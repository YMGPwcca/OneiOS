# The thermal bridge (README.md).
#   make test       host unit tests (ASan, UBSan): the limits, the rules and their hysteresis, the CPU steps, a fake sysfs,
#                   the worker's listeners
#   make            build/android/thermalctl (static; the phone tool)
include $(dir $(lastword $(MAKEFILE_LIST)))../../host.mk
ANDROID_CC ?= $(TOOLS)/aarch64-linux-android30-clang
WARN := -Wall -Wextra -Werror
INC := -I. -I../include
SRC := thermal.c ../cpu/topology.c ../hw/hw_backend.c ../hw/hw_log.c ../hal/hal.c ../wifi/aidl_parcel.c ../wifi/aidl_binder.c
HDR := thermal.h ../include/bridges/bridges.h ../include/bridges/hw_backend.h ../hal/hal.h ../wifi/aidl.h

all: build/android/thermalctl
build/android/thermalctl: thermalctl.c $(SRC) $(HDR)
	@mkdir -p $(dir $@)
	$(ANDROID_CC) -std=gnu11 -O2 -g $(WARN) $(INC) -static thermalctl.c $(SRC) -o $@
build/host/test_thermal: test_thermal.c $(SRC) $(HDR)
	@mkdir -p $(dir $@)
	$(CC) -std=gnu11 -O1 -g $(WARN) $(INC) -fsanitize=address,undefined test_thermal.c $(SRC) -lpthread -o $@
build/host/thermalctl: thermalctl.c $(SRC) $(HDR)
	@mkdir -p $(dir $@)
	$(CC) -std=gnu11 -O1 -g $(WARN) $(INC) -fsanitize=address,undefined thermalctl.c $(SRC) -lpthread -o $@
test: build/host/test_thermal build/host/thermalctl
	build/host/test_thermal
	python3 test_native_thermalctl.py build/host/thermalctl
clean:
	rm -rf build
.PHONY: all test clean

# Explicit cross-repository stock thermal integration tests. Ordinary
# thermalctl and standalone bridge builds do not acquire an app dependency.
ONEOS_NATIVE := ../../../app/switcher/native
STOCK_HDR := stock_hal.h $(ONEOS_NATIVE)/sm8850_thermal_controller.h $(ONEOS_NATIVE)/sm8850_owned_groups.h
build/host/test_stock_hal: test_stock_hal.c stock_hal.c $(SRC) $(HDR) $(STOCK_HDR)
	@mkdir -p $(dir $@)
	$(CC) -std=gnu11 -O1 -g $(WARN) $(INC) -I$(ONEOS_NATIVE) -fsanitize=address,undefined test_stock_hal.c stock_hal.c $(SRC) -lpthread -o $@
build/android/stock_hal.o: stock_hal.c $(HDR) $(STOCK_HDR)
	@mkdir -p $(dir $@)
	$(ANDROID_CC) -std=gnu11 -O2 -g $(WARN) $(INC) -I$(ONEOS_NATIVE) -c stock_hal.c -o $@
stock-test: build/host/test_stock_hal build/android/stock_hal.o
	build/host/test_stock_hal
.PHONY: stock-test
