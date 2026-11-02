// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2.1 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2026 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
// control
// 0x00 : Control signals
//        bit 0  - ap_start (Read/Write/COH)
//        bit 1  - ap_done (Read/COR)
//        bit 2  - ap_idle (Read)
//        bit 3  - ap_ready (Read/COR)
//        bit 7  - auto_restart (Read/Write)
//        bit 9  - interrupt (Read)
//        others - reserved
// 0x04 : Global Interrupt Enable Register
//        bit 0  - Global Interrupt Enable (Read/Write)
//        others - reserved
// 0x08 : IP Interrupt Enable Register (Read/Write)
//        bit 0 - enable ap_done interrupt (Read/Write)
//        bit 1 - enable ap_ready interrupt (Read/Write)
//        others - reserved
// 0x0c : IP Interrupt Status Register (Read/TOW)
//        bit 0 - ap_done (Read/TOW)
//        bit 1 - ap_ready (Read/TOW)
//        others - reserved
// 0x10 : Data signal of nx
//        bit 31~0 - nx[31:0] (Read/Write)
// 0x14 : reserved
// 0x18 : Data signal of ny
//        bit 31~0 - ny[31:0] (Read/Write)
// 0x1c : reserved
// 0x20 : Data signal of nz
//        bit 31~0 - nz[31:0] (Read/Write)
// 0x24 : reserved
// 0x28 : Data signal of capacity_triangles
//        bit 31~0 - capacity_triangles[31:0] (Read/Write)
// 0x2c : reserved
// 0x30 : Data signal of count_only
//        bit 31~0 - count_only[31:0] (Read/Write)
// 0x34 : reserved
// 0x38 : Data signal of expected_triangles
//        bit 31~0 - expected_triangles[31:0] (Read/Write)
// 0x3c : reserved
// 0x40 : Data signal of input_words
//        bit 31~0 - input_words[31:0] (Read/Write)
// 0x44 : reserved
// (SC = Self Clear, COR = Clear on Read, TOW = Toggle on Write, COH = Clear on Handshake)

#define XBINARY_MC_AXIS_CONTROL_ADDR_AP_CTRL                 0x00
#define XBINARY_MC_AXIS_CONTROL_ADDR_GIE                     0x04
#define XBINARY_MC_AXIS_CONTROL_ADDR_IER                     0x08
#define XBINARY_MC_AXIS_CONTROL_ADDR_ISR                     0x0c
#define XBINARY_MC_AXIS_CONTROL_ADDR_NX_DATA                 0x10
#define XBINARY_MC_AXIS_CONTROL_BITS_NX_DATA                 32
#define XBINARY_MC_AXIS_CONTROL_ADDR_NY_DATA                 0x18
#define XBINARY_MC_AXIS_CONTROL_BITS_NY_DATA                 32
#define XBINARY_MC_AXIS_CONTROL_ADDR_NZ_DATA                 0x20
#define XBINARY_MC_AXIS_CONTROL_BITS_NZ_DATA                 32
#define XBINARY_MC_AXIS_CONTROL_ADDR_CAPACITY_TRIANGLES_DATA 0x28
#define XBINARY_MC_AXIS_CONTROL_BITS_CAPACITY_TRIANGLES_DATA 32
#define XBINARY_MC_AXIS_CONTROL_ADDR_COUNT_ONLY_DATA         0x30
#define XBINARY_MC_AXIS_CONTROL_BITS_COUNT_ONLY_DATA         32
#define XBINARY_MC_AXIS_CONTROL_ADDR_EXPECTED_TRIANGLES_DATA 0x38
#define XBINARY_MC_AXIS_CONTROL_BITS_EXPECTED_TRIANGLES_DATA 32
#define XBINARY_MC_AXIS_CONTROL_ADDR_INPUT_WORDS_DATA        0x40
#define XBINARY_MC_AXIS_CONTROL_BITS_INPUT_WORDS_DATA        32

