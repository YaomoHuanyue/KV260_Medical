// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2.1 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2026 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef XDFX_WRITER_H
#define XDFX_WRITER_H

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
#include "xdfx_writer_hw.h"

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
} XDfx_writer_Config;
#endif

typedef struct {
    u64 Control_BaseAddress;
    u32 IsReady;
} XDfx_writer;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XDfx_writer_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XDfx_writer_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XDfx_writer_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XDfx_writer_ReadReg(BaseAddress, RegOffset) \
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
int XDfx_writer_Initialize(XDfx_writer *InstancePtr, UINTPTR BaseAddress);
XDfx_writer_Config* XDfx_writer_LookupConfig(UINTPTR BaseAddress);
#else
int XDfx_writer_Initialize(XDfx_writer *InstancePtr, u16 DeviceId);
XDfx_writer_Config* XDfx_writer_LookupConfig(u16 DeviceId);
#endif
int XDfx_writer_CfgInitialize(XDfx_writer *InstancePtr, XDfx_writer_Config *ConfigPtr);
#else
int XDfx_writer_Initialize(XDfx_writer *InstancePtr, const char* InstanceName);
int XDfx_writer_Release(XDfx_writer *InstancePtr);
#endif

void XDfx_writer_Start(XDfx_writer *InstancePtr);
u32 XDfx_writer_IsDone(XDfx_writer *InstancePtr);
u32 XDfx_writer_IsIdle(XDfx_writer *InstancePtr);
u32 XDfx_writer_IsReady(XDfx_writer *InstancePtr);
void XDfx_writer_EnableAutoRestart(XDfx_writer *InstancePtr);
void XDfx_writer_DisableAutoRestart(XDfx_writer *InstancePtr);

void XDfx_writer_Set_output_r(XDfx_writer *InstancePtr, u64 Data);
u64 XDfx_writer_Get_output_r(XDfx_writer *InstancePtr);
void XDfx_writer_Set_count(XDfx_writer *InstancePtr, u32 Data);
u32 XDfx_writer_Get_count(XDfx_writer *InstancePtr);
u32 XDfx_writer_Get_status(XDfx_writer *InstancePtr);
u32 XDfx_writer_Get_status_vld(XDfx_writer *InstancePtr);

void XDfx_writer_InterruptGlobalEnable(XDfx_writer *InstancePtr);
void XDfx_writer_InterruptGlobalDisable(XDfx_writer *InstancePtr);
void XDfx_writer_InterruptEnable(XDfx_writer *InstancePtr, u32 Mask);
void XDfx_writer_InterruptDisable(XDfx_writer *InstancePtr, u32 Mask);
void XDfx_writer_InterruptClear(XDfx_writer *InstancePtr, u32 Mask);
u32 XDfx_writer_InterruptGetEnabled(XDfx_writer *InstancePtr);
u32 XDfx_writer_InterruptGetStatus(XDfx_writer *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
