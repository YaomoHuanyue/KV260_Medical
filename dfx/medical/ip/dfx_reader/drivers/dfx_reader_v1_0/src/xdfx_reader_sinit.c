// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2.1 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2026 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef __linux__

#include "xstatus.h"
#ifdef SDT
#include "xparameters.h"
#endif
#include "xdfx_reader.h"

extern XDfx_reader_Config XDfx_reader_ConfigTable[];

#ifdef SDT
XDfx_reader_Config *XDfx_reader_LookupConfig(UINTPTR BaseAddress) {
	XDfx_reader_Config *ConfigPtr = NULL;

	int Index;

	for (Index = (u32)0x0; XDfx_reader_ConfigTable[Index].Name != NULL; Index++) {
		if (!BaseAddress || XDfx_reader_ConfigTable[Index].Control_BaseAddress == BaseAddress) {
			ConfigPtr = &XDfx_reader_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XDfx_reader_Initialize(XDfx_reader *InstancePtr, UINTPTR BaseAddress) {
	XDfx_reader_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XDfx_reader_LookupConfig(BaseAddress);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XDfx_reader_CfgInitialize(InstancePtr, ConfigPtr);
}
#else
XDfx_reader_Config *XDfx_reader_LookupConfig(u16 DeviceId) {
	XDfx_reader_Config *ConfigPtr = NULL;

	int Index;

	for (Index = 0; Index < XPAR_XDFX_READER_NUM_INSTANCES; Index++) {
		if (XDfx_reader_ConfigTable[Index].DeviceId == DeviceId) {
			ConfigPtr = &XDfx_reader_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XDfx_reader_Initialize(XDfx_reader *InstancePtr, u16 DeviceId) {
	XDfx_reader_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XDfx_reader_LookupConfig(DeviceId);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XDfx_reader_CfgInitialize(InstancePtr, ConfigPtr);
}
#endif

#endif

