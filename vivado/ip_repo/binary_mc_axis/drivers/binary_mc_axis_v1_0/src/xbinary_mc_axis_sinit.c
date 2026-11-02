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
#include "xbinary_mc_axis.h"

extern XBinary_mc_axis_Config XBinary_mc_axis_ConfigTable[];

#ifdef SDT
XBinary_mc_axis_Config *XBinary_mc_axis_LookupConfig(UINTPTR BaseAddress) {
	XBinary_mc_axis_Config *ConfigPtr = NULL;

	int Index;

	for (Index = (u32)0x0; XBinary_mc_axis_ConfigTable[Index].Name != NULL; Index++) {
		if (!BaseAddress || XBinary_mc_axis_ConfigTable[Index].Control_BaseAddress == BaseAddress) {
			ConfigPtr = &XBinary_mc_axis_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XBinary_mc_axis_Initialize(XBinary_mc_axis *InstancePtr, UINTPTR BaseAddress) {
	XBinary_mc_axis_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XBinary_mc_axis_LookupConfig(BaseAddress);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XBinary_mc_axis_CfgInitialize(InstancePtr, ConfigPtr);
}
#else
XBinary_mc_axis_Config *XBinary_mc_axis_LookupConfig(u16 DeviceId) {
	XBinary_mc_axis_Config *ConfigPtr = NULL;

	int Index;

	for (Index = 0; Index < XPAR_XBINARY_MC_AXIS_NUM_INSTANCES; Index++) {
		if (XBinary_mc_axis_ConfigTable[Index].DeviceId == DeviceId) {
			ConfigPtr = &XBinary_mc_axis_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XBinary_mc_axis_Initialize(XBinary_mc_axis *InstancePtr, u16 DeviceId) {
	XBinary_mc_axis_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XBinary_mc_axis_LookupConfig(DeviceId);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XBinary_mc_axis_CfgInitialize(InstancePtr, ConfigPtr);
}
#endif

#endif

