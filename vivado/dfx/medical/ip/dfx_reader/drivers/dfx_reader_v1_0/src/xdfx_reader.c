// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2.1 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2026 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
/***************************** Include Files *********************************/
#include "xdfx_reader.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XDfx_reader_CfgInitialize(XDfx_reader *InstancePtr, XDfx_reader_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Control_BaseAddress = ConfigPtr->Control_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XDfx_reader_Start(XDfx_reader *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDfx_reader_ReadReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_AP_CTRL) & 0x80;
    XDfx_reader_WriteReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XDfx_reader_IsDone(XDfx_reader *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDfx_reader_ReadReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XDfx_reader_IsIdle(XDfx_reader *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDfx_reader_ReadReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XDfx_reader_IsReady(XDfx_reader *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDfx_reader_ReadReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XDfx_reader_EnableAutoRestart(XDfx_reader *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDfx_reader_WriteReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_AP_CTRL, 0x80);
}

void XDfx_reader_DisableAutoRestart(XDfx_reader *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDfx_reader_WriteReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_AP_CTRL, 0);
}

void XDfx_reader_Set_input_r(XDfx_reader *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDfx_reader_WriteReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_INPUT_R_DATA, (u32)(Data));
    XDfx_reader_WriteReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_INPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XDfx_reader_Get_input_r(XDfx_reader *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDfx_reader_ReadReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_INPUT_R_DATA);
    Data += (u64)XDfx_reader_ReadReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_INPUT_R_DATA + 4) << 32;
    return Data;
}

void XDfx_reader_Set_count(XDfx_reader *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDfx_reader_WriteReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_COUNT_DATA, Data);
}

u32 XDfx_reader_Get_count(XDfx_reader *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDfx_reader_ReadReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_COUNT_DATA);
    return Data;
}

void XDfx_reader_InterruptGlobalEnable(XDfx_reader *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDfx_reader_WriteReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_GIE, 1);
}

void XDfx_reader_InterruptGlobalDisable(XDfx_reader *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDfx_reader_WriteReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_GIE, 0);
}

void XDfx_reader_InterruptEnable(XDfx_reader *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XDfx_reader_ReadReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_IER);
    XDfx_reader_WriteReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_IER, Register | Mask);
}

void XDfx_reader_InterruptDisable(XDfx_reader *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XDfx_reader_ReadReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_IER);
    XDfx_reader_WriteReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_IER, Register & (~Mask));
}

void XDfx_reader_InterruptClear(XDfx_reader *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDfx_reader_WriteReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_ISR, Mask);
}

u32 XDfx_reader_InterruptGetEnabled(XDfx_reader *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XDfx_reader_ReadReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_IER);
}

u32 XDfx_reader_InterruptGetStatus(XDfx_reader *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XDfx_reader_ReadReg(InstancePtr->Control_BaseAddress, XDFX_READER_CONTROL_ADDR_ISR);
}

