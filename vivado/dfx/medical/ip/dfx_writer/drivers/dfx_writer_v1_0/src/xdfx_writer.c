// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2.1 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2026 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
/***************************** Include Files *********************************/
#include "xdfx_writer.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XDfx_writer_CfgInitialize(XDfx_writer *InstancePtr, XDfx_writer_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Control_BaseAddress = ConfigPtr->Control_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XDfx_writer_Start(XDfx_writer *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDfx_writer_ReadReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_AP_CTRL) & 0x80;
    XDfx_writer_WriteReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XDfx_writer_IsDone(XDfx_writer *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDfx_writer_ReadReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XDfx_writer_IsIdle(XDfx_writer *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDfx_writer_ReadReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XDfx_writer_IsReady(XDfx_writer *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDfx_writer_ReadReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XDfx_writer_EnableAutoRestart(XDfx_writer *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDfx_writer_WriteReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_AP_CTRL, 0x80);
}

void XDfx_writer_DisableAutoRestart(XDfx_writer *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDfx_writer_WriteReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_AP_CTRL, 0);
}

void XDfx_writer_Set_output_r(XDfx_writer *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDfx_writer_WriteReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_OUTPUT_R_DATA, (u32)(Data));
    XDfx_writer_WriteReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_OUTPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XDfx_writer_Get_output_r(XDfx_writer *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDfx_writer_ReadReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_OUTPUT_R_DATA);
    Data += (u64)XDfx_writer_ReadReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_OUTPUT_R_DATA + 4) << 32;
    return Data;
}

void XDfx_writer_Set_count(XDfx_writer *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDfx_writer_WriteReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_COUNT_DATA, Data);
}

u32 XDfx_writer_Get_count(XDfx_writer *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDfx_writer_ReadReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_COUNT_DATA);
    return Data;
}

u32 XDfx_writer_Get_status(XDfx_writer *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDfx_writer_ReadReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_STATUS_DATA);
    return Data;
}

u32 XDfx_writer_Get_status_vld(XDfx_writer *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDfx_writer_ReadReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_STATUS_CTRL);
    return Data & 0x1;
}

void XDfx_writer_InterruptGlobalEnable(XDfx_writer *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDfx_writer_WriteReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_GIE, 1);
}

void XDfx_writer_InterruptGlobalDisable(XDfx_writer *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDfx_writer_WriteReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_GIE, 0);
}

void XDfx_writer_InterruptEnable(XDfx_writer *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XDfx_writer_ReadReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_IER);
    XDfx_writer_WriteReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_IER, Register | Mask);
}

void XDfx_writer_InterruptDisable(XDfx_writer *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XDfx_writer_ReadReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_IER);
    XDfx_writer_WriteReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_IER, Register & (~Mask));
}

void XDfx_writer_InterruptClear(XDfx_writer *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDfx_writer_WriteReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_ISR, Mask);
}

u32 XDfx_writer_InterruptGetEnabled(XDfx_writer *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XDfx_writer_ReadReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_IER);
}

u32 XDfx_writer_InterruptGetStatus(XDfx_writer *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XDfx_writer_ReadReg(InstancePtr->Control_BaseAddress, XDFX_WRITER_CONTROL_ADDR_ISR);
}

