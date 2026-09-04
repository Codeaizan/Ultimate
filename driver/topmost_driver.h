/*
 * topmost_driver.h
 * ================
 * Shared definitions between the TopMost kernel driver and user-mode application.
 * IOCTL codes, data structures, and constants.
 *
 * Copyright (c) 2026 TopMost Shield Project
 */

#pragma once

#ifndef TOPMOST_DRIVER_H
#define TOPMOST_DRIVER_H

/* ─── Device Naming ─────────────────────────────────────────────────────── */

#define TOPMOST_DEVICE_NAME     L"\\Device\\TopMostDriver"
#define TOPMOST_SYMLINK_NAME    L"\\DosDevices\\TopMostDriver"
#define TOPMOST_WIN32_NAME      L"\\\\.\\TopMostDriver"

/* ─── IOCTL Codes ───────────────────────────────────────────────────────── */

/*
 * We use FILE_DEVICE_UNKNOWN (0x00000022) as our device type.
 * Function codes 0x800-0xFFF are reserved for customer use.
 * All IOCTLs use METHOD_BUFFERED for simplicity and safety.
 */

#define TOPMOST_IOCTL_TYPE  FILE_DEVICE_UNKNOWN

/*
 * IOCTL_TOPMOST_BOOST_PRIORITY
 * ----------------------------
 * Boosts the calling process and its threads to the highest possible
 * scheduling priority (REALTIME class, priority level 26).
 *
 * Input:  None
 * Output: TOPMOST_STATUS structure
 */
#define IOCTL_TOPMOST_BOOST_PRIORITY \
    CTL_CODE(TOPMOST_IOCTL_TYPE, 0x800, METHOD_BUFFERED, FILE_ANY_ACCESS)

/*
 * IOCTL_TOPMOST_RESET_PRIORITY
 * ----------------------------
 * Resets the calling process priority back to NORMAL.
 *
 * Input:  None
 * Output: TOPMOST_STATUS structure
 */
#define IOCTL_TOPMOST_RESET_PRIORITY \
    CTL_CODE(TOPMOST_IOCTL_TYPE, 0x801, METHOD_BUFFERED, FILE_ANY_ACCESS)

/*
 * IOCTL_TOPMOST_GET_STATUS
 * ------------------------
 * Returns the current driver status and information about the protected process.
 *
 * Input:  None
 * Output: TOPMOST_STATUS structure
 */
#define IOCTL_TOPMOST_GET_STATUS \
    CTL_CODE(TOPMOST_IOCTL_TYPE, 0x802, METHOD_BUFFERED, FILE_ANY_ACCESS)

/*
 * IOCTL_TOPMOST_SET_PROTECTED_PID
 * --------------------------------
 * Registers a process ID for protection. The driver will monitor this PID
 * and prevent priority degradation.
 *
 * Input:  ULONG (Process ID)
 * Output: TOPMOST_STATUS structure
 */
#define IOCTL_TOPMOST_SET_PROTECTED_PID \
    CTL_CODE(TOPMOST_IOCTL_TYPE, 0x803, METHOD_BUFFERED, FILE_ANY_ACCESS)

/* ─── Data Structures ───────────────────────────────────────────────────── */

/*
 * TOPMOST_STATUS
 * Returned by all IOCTLs to report current driver state.
 */
typedef struct _TOPMOST_STATUS {
    ULONG   Version;            /* Driver version (major << 16 | minor) */
    ULONG   IsActive;           /* 1 if driver is actively protecting */
    ULONG   ProtectedPid;       /* Currently protected process ID (0 = none) */
    ULONG   CurrentPriority;    /* Current priority of the protected process */
    ULONG   BoostCount;         /* Number of priority boosts performed */
    ULONG   Reserved[3];        /* Reserved for future use */
} TOPMOST_STATUS, *PTOPMOST_STATUS;

/* ─── Constants ─────────────────────────────────────────────────────────── */

#define TOPMOST_DRIVER_VERSION_MAJOR    1
#define TOPMOST_DRIVER_VERSION_MINOR    0
#define TOPMOST_DRIVER_VERSION          ((TOPMOST_DRIVER_VERSION_MAJOR << 16) | TOPMOST_DRIVER_VERSION_MINOR)

/* Priority level we boost to (LOW_REALTIME_PRIORITY + 10 = 26) */
#define TOPMOST_BOOST_PRIORITY_LEVEL    26

/* Maximum priority level (31 is reserved for zero-page thread) */
#define TOPMOST_MAX_PRIORITY_LEVEL      30

#endif /* TOPMOST_DRIVER_H */
