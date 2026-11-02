// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2.1 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2026 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
/***************************** Include Files *********************************/
#include "xbinary_mc_axis.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XBinary_mc_axis_CfgInitialize(XBinary_mc_axis *InstancePtr, XBinary_mc_axis_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Control_BaseAddress = ConfigPtr->Control_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XBinary_mc_axis_Start(XBinary_mc_axis *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_AP_CTRL) & 0x80;
    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XBinary_mc_axis_IsDone(XBinary_mc_axis *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XBinary_mc_axis_IsIdle(XBinary_mc_axis *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XBinary_mc_axis_IsReady(XBinary_mc_axis *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XBinary_mc_axis_EnableAutoRestart(XBinary_mc_axis *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_AP_CTRL, 0x80);
}

void XBinary_mc_axis_DisableAutoRestart(XBinary_mc_axis *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_AP_CTRL, 0);
}

void XBinary_mc_axis_Set_nx(XBinary_mc_axis *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_NX_DATA, Data);
}

u32 XBinary_mc_axis_Get_nx(XBinary_mc_axis *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_NX_DATA);
    return Data;
}

void XBinary_mc_axis_Set_ny(XBinary_mc_axis *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_NY_DATA, Data);
}

u32 XBinary_mc_axis_Get_ny(XBinary_mc_axis *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_NY_DATA);
    return Data;
}

void XBinary_mc_axis_Set_nz(XBinary_mc_axis *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_NZ_DATA, Data);
}

u32 XBinary_mc_axis_Get_nz(XBinary_mc_axis *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_NZ_DATA);
    return Data;
}

void XBinary_mc_axis_Set_capacity_triangles(XBinary_mc_axis *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_CAPACITY_TRIANGLES_DATA, Data);
}

u32 XBinary_mc_axis_Get_capacity_triangles(XBinary_mc_axis *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_CAPACITY_TRIANGLES_DATA);
    return Data;
}

void XBinary_mc_axis_Set_count_only(XBinary_mc_axis *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_COUNT_ONLY_DATA, Data);
}

u32 XBinary_mc_axis_Get_count_only(XBinary_mc_axis *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_COUNT_ONLY_DATA);
    return Data;
}

void XBinary_mc_axis_Set_expected_triangles(XBinary_mc_axis *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_EXPECTED_TRIANGLES_DATA, Data);
}

u32 XBinary_mc_axis_Get_expected_triangles(XBinary_mc_axis *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_EXPECTED_TRIANGLES_DATA);
    return Data;
}

void XBinary_mc_axis_Set_input_words(XBinary_mc_axis *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_INPUT_WORDS_DATA, Data);
}

u32 XBinary_mc_axis_Get_input_words(XBinary_mc_axis *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_INPUT_WORDS_DATA);
    return Data;
}

void XBinary_mc_axis_InterruptGlobalEnable(XBinary_mc_axis *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_GIE, 1);
}

void XBinary_mc_axis_InterruptGlobalDisable(XBinary_mc_axis *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_GIE, 0);
}

void XBinary_mc_axis_InterruptEnable(XBinary_mc_axis *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_IER);
    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_IER, Register | Mask);
}

void XBinary_mc_axis_InterruptDisable(XBinary_mc_axis *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_IER);
    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_IER, Register & (~Mask));
}

void XBinary_mc_axis_InterruptClear(XBinary_mc_axis *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBinary_mc_axis_WriteReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_ISR, Mask);
}

u32 XBinary_mc_axis_InterruptGetEnabled(XBinary_mc_axis *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_IER);
}

u32 XBinary_mc_axis_InterruptGetStatus(XBinary_mc_axis *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XBinary_mc_axis_ReadReg(InstancePtr->Control_BaseAddress, XBINARY_MC_AXIS_CONTROL_ADDR_ISR);
}

