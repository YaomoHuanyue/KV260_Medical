// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2.1 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2026 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef XBINARY_MC_AXIS_H
#define XBINARY_MC_AXIS_H

#ifdef __cplusplus
extern "C" {
#endif

/***************************** Include Files *********************************/
#ifndef __linux__
#include "xil_types.h"
#include "xil_assert.h"
#include "xstatus.h"
#include "xil_io.h"
#else
#include <stdint.h>
#include <assert.h>
#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stddef.h>
#endif
#include "xbinary_mc_axis_hw.h"

/**************************** Type Definitions ******************************/
#ifdef __linux__
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#else
typedef struct {
#ifdef SDT
    char *Name;
#else
    u16 DeviceId;
#endif
    u64 Control_BaseAddress;
} XBinary_mc_axis_Config;
#endif

typedef struct {
    u64 Control_BaseAddress;
    u32 IsReady;
} XBinary_mc_axis;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XBinary_mc_axis_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XBinary_mc_axis_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XBinary_mc_axis_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XBinary_mc_axis_ReadReg(BaseAddress, RegOffset) \
    *(volatile u32*)((BaseAddress) + (RegOffset))

#define Xil_AssertVoid(expr)    assert(expr)
#define Xil_AssertNonvoid(expr) assert(expr)

#define XST_SUCCESS             0
#define XST_DEVICE_NOT_FOUND    2
#define XST_OPEN_DEVICE_FAILED  3
#define XIL_COMPONENT_IS_READY  1
#endif

/************************** Function Prototypes *****************************/
#ifndef __linux__
#ifdef SDT
int XBinary_mc_axis_Initialize(XBinary_mc_axis *InstancePtr, UINTPTR BaseAddress);
XBinary_mc_axis_Config* XBinary_mc_axis_LookupConfig(UINTPTR BaseAddress);
#else
int XBinary_mc_axis_Initialize(XBinary_mc_axis *InstancePtr, u16 DeviceId);
XBinary_mc_axis_Config* XBinary_mc_axis_LookupConfig(u16 DeviceId);
#endif
int XBinary_mc_axis_CfgInitialize(XBinary_mc_axis *InstancePtr, XBinary_mc_axis_Config *ConfigPtr);
#else
int XBinary_mc_axis_Initialize(XBinary_mc_axis *InstancePtr, const char* InstanceName);
int XBinary_mc_axis_Release(XBinary_mc_axis *InstancePtr);
#endif

void XBinary_mc_axis_Start(XBinary_mc_axis *InstancePtr);
u32 XBinary_mc_axis_IsDone(XBinary_mc_axis *InstancePtr);
u32 XBinary_mc_axis_IsIdle(XBinary_mc_axis *InstancePtr);
u32 XBinary_mc_axis_IsReady(XBinary_mc_axis *InstancePtr);
void XBinary_mc_axis_EnableAutoRestart(XBinary_mc_axis *InstancePtr);
void XBinary_mc_axis_DisableAutoRestart(XBinary_mc_axis *InstancePtr);

void XBinary_mc_axis_Set_nx(XBinary_mc_axis *InstancePtr, u32 Data);
u32 XBinary_mc_axis_Get_nx(XBinary_mc_axis *InstancePtr);
void XBinary_mc_axis_Set_ny(XBinary_mc_axis *InstancePtr, u32 Data);
u32 XBinary_mc_axis_Get_ny(XBinary_mc_axis *InstancePtr);
void XBinary_mc_axis_Set_nz(XBinary_mc_axis *InstancePtr, u32 Data);
u32 XBinary_mc_axis_Get_nz(XBinary_mc_axis *InstancePtr);
void XBinary_mc_axis_Set_capacity_triangles(XBinary_mc_axis *InstancePtr, u32 Data);
u32 XBinary_mc_axis_Get_capacity_triangles(XBinary_mc_axis *InstancePtr);
void XBinary_mc_axis_Set_count_only(XBinary_mc_axis *InstancePtr, u32 Data);
u32 XBinary_mc_axis_Get_count_only(XBinary_mc_axis *InstancePtr);
void XBinary_mc_axis_Set_expected_triangles(XBinary_mc_axis *InstancePtr, u32 Data);
u32 XBinary_mc_axis_Get_expected_triangles(XBinary_mc_axis *InstancePtr);
void XBinary_mc_axis_Set_input_words(XBinary_mc_axis *InstancePtr, u32 Data);
u32 XBinary_mc_axis_Get_input_words(XBinary_mc_axis *InstancePtr);

void XBinary_mc_axis_InterruptGlobalEnable(XBinary_mc_axis *InstancePtr);
void XBinary_mc_axis_InterruptGlobalDisable(XBinary_mc_axis *InstancePtr);
void XBinary_mc_axis_InterruptEnable(XBinary_mc_axis *InstancePtr, u32 Mask);
void XBinary_mc_axis_InterruptDisable(XBinary_mc_axis *InstancePtr, u32 Mask);
void XBinary_mc_axis_InterruptClear(XBinary_mc_axis *InstancePtr, u32 Mask);
u32 XBinary_mc_axis_InterruptGetEnabled(XBinary_mc_axis *InstancePtr);
u32 XBinary_mc_axis_InterruptGetStatus(XBinary_mc_axis *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
