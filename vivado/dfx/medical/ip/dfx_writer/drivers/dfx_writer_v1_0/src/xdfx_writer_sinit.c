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
#include "xdfx_writer.h"

extern XDfx_writer_Config XDfx_writer_ConfigTable[];

#ifdef SDT
XDfx_writer_Config *XDfx_writer_LookupConfig(UINTPTR BaseAddress) {
	XDfx_writer_Config *ConfigPtr = NULL;

	int Index;

	for (Index = (u32)0x0; XDfx_writer_ConfigTable[Index].Name != NULL; Index++) {
		if (!BaseAddress || XDfx_writer_ConfigTable[Index].Control_BaseAddress == BaseAddress) {
			ConfigPtr = &XDfx_writer_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XDfx_writer_Initialize(XDfx_writer *InstancePtr, UINTPTR BaseAddress) {
	XDfx_writer_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XDfx_writer_LookupConfig(BaseAddress);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XDfx_writer_CfgInitialize(InstancePtr, ConfigPtr);
}
#else
XDfx_writer_Config *XDfx_writer_LookupConfig(u16 DeviceId) {
	XDfx_writer_Config *ConfigPtr = NULL;

	int Index;

	for (Index = 0; Index < XPAR_XDFX_WRITER_NUM_INSTANCES; Index++) {
		if (XDfx_writer_ConfigTable[Index].DeviceId == DeviceId) {
			ConfigPtr = &XDfx_writer_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XDfx_writer_Initialize(XDfx_writer *InstancePtr, u16 DeviceId) {
	XDfx_writer_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XDfx_writer_LookupConfig(DeviceId);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XDfx_writer_CfgInitialize(InstancePtr, ConfigPtr);
}
#endif

#endif

