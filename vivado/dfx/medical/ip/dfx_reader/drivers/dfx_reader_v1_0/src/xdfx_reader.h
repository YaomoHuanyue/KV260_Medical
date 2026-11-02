// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2.1 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2026 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef XDFX_READER_H
#define XDFX_READER_H

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
#include "xdfx_reader_hw.h"

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
} XDfx_reader_Config;
#endif

typedef struct {
    u64 Control_BaseAddress;
    u32 IsReady;
} XDfx_reader;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XDfx_reader_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XDfx_reader_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XDfx_reader_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XDfx_reader_ReadReg(BaseAddress, RegOffset) \
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
int XDfx_reader_Initialize(XDfx_reader *InstancePtr, UINTPTR BaseAddress);
XDfx_reader_Config* XDfx_reader_LookupConfig(UINTPTR BaseAddress);
#else
int XDfx_reader_Initialize(XDfx_reader *InstancePtr, u16 DeviceId);
XDfx_reader_Config* XDfx_reader_LookupConfig(u16 DeviceId);
#endif
int XDfx_reader_CfgInitialize(XDfx_reader *InstancePtr, XDfx_reader_Config *ConfigPtr);
#else
int XDfx_reader_Initialize(XDfx_reader *InstancePtr, const char* InstanceName);
int XDfx_reader_Release(XDfx_reader *InstancePtr);
#endif

void XDfx_reader_Start(XDfx_reader *InstancePtr);
u32 XDfx_reader_IsDone(XDfx_reader *InstancePtr);
u32 XDfx_reader_IsIdle(XDfx_reader *InstancePtr);
u32 XDfx_reader_IsReady(XDfx_reader *InstancePtr);
void XDfx_reader_EnableAutoRestart(XDfx_reader *InstancePtr);
void XDfx_reader_DisableAutoRestart(XDfx_reader *InstancePtr);

void XDfx_reader_Set_input_r(XDfx_reader *InstancePtr, u64 Data);
u64 XDfx_reader_Get_input_r(XDfx_reader *InstancePtr);
void XDfx_reader_Set_count(XDfx_reader *InstancePtr, u32 Data);
u32 XDfx_reader_Get_count(XDfx_reader *InstancePtr);

void XDfx_reader_InterruptGlobalEnable(XDfx_reader *InstancePtr);
void XDfx_reader_InterruptGlobalDisable(XDfx_reader *InstancePtr);
void XDfx_reader_InterruptEnable(XDfx_reader *InstancePtr, u32 Mask);
void XDfx_reader_InterruptDisable(XDfx_reader *InstancePtr, u32 Mask);
void XDfx_reader_InterruptClear(XDfx_reader *InstancePtr, u32 Mask);
u32 XDfx_reader_InterruptGetEnabled(XDfx_reader *InstancePtr);
u32 XDfx_reader_InterruptGetStatus(XDfx_reader *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
