/*
 * topmost_driver.c
 * =================
 * Windows Kernel-Mode Driver (WDM) for TopMost Shield.
 *
 * This driver provides kernel-level enforcement for keeping a user-mode
 * window always on top of all other windows by:
 *
 * 1. Boosting the owning process/thread to REALTIME scheduling priority
 * 2. Monitoring process creation to detect competing topmost applications
 * 3. Providing a stable communication channel via IOCTLs
 *
 * Build Requirements:
 *   - Visual Studio 2022 + Windows Driver Kit (WDK)
 *   - Target: Windows 10/11 x64
 *
 * Copyright (c) 2026 TopMost Shield Project
 */

#include <ntddk.h>
#include "topmost_driver.h"

/* ─── Driver Tag for Memory Allocations ─────────────────────────────────── */
#define TOPMOST_TAG 'tsMT'

/* Process access rights (not defined in kernel headers) */
#ifndef PROCESS_TERMINATE
#define PROCESS_TERMINATE           0x0001
#endif
#ifndef PROCESS_SUSPEND_RESUME
#define PROCESS_SUSPEND_RESUME      0x0800
#endif

/* ─── Global Driver State ───────────────────────────────────────────────── */

typedef struct _TOPMOST_DRIVER_CONTEXT {
    PDEVICE_OBJECT  DeviceObject;
    BOOLEAN         IsActive;
    HANDLE          ProtectedPid;
    KPRIORITY       OriginalPriority;
    ULONG           BoostCount;
    BOOLEAN         ProcessCallbackRegistered;
    PVOID           ObCallbackHandle;       /* ObRegisterCallbacks handle */
    BOOLEAN         ObCallbackRegistered;
} TOPMOST_DRIVER_CONTEXT, *PTOPMOST_DRIVER_CONTEXT;

static TOPMOST_DRIVER_CONTEXT g_DriverContext = { 0 };

/* ─── Forward Declarations ──────────────────────────────────────────────── */

DRIVER_INITIALIZE   DriverEntry;
DRIVER_UNLOAD       TopMostDriverUnload;

_Dispatch_type_(IRP_MJ_CREATE)
DRIVER_DISPATCH     TopMostDispatchCreate;

_Dispatch_type_(IRP_MJ_CLOSE)
DRIVER_DISPATCH     TopMostDispatchClose;

_Dispatch_type_(IRP_MJ_DEVICE_CONTROL)
DRIVER_DISPATCH     TopMostDispatchDeviceControl;

VOID TopMostProcessNotifyCallback(
    _Inout_  PEPROCESS               Process,
    _In_     HANDLE                  ProcessId,
    _In_opt_ PPS_CREATE_NOTIFY_INFO  CreateInfo
);

OB_PREOP_CALLBACK_STATUS
TopMostObPreOperationCallback(
    _In_ PVOID                          RegistrationContext,
    _Inout_ POB_PRE_OPERATION_INFORMATION OperationInformation
);

/* ─── Helper: Fill Status Structure ─────────────────────────────────────── */

static VOID
TopMostFillStatus(
    _Out_ PTOPMOST_STATUS Status
)
{
    RtlZeroMemory(Status, sizeof(TOPMOST_STATUS));
    Status->Version         = TOPMOST_DRIVER_VERSION;
    Status->IsActive        = g_DriverContext.IsActive ? 1 : 0;
    Status->ProtectedPid    = (ULONG)(ULONG_PTR)g_DriverContext.ProtectedPid;
    Status->BoostCount      = g_DriverContext.BoostCount;

    /* Try to get current priority of the protected process */
    if (g_DriverContext.ProtectedPid != NULL) {
        PEPROCESS process = NULL;
        NTSTATUS status = PsLookupProcessByProcessId(
            g_DriverContext.ProtectedPid, &process);
        if (NT_SUCCESS(status) && process != NULL) {
            /* Report the boosted priority level */
            Status->CurrentPriority = TOPMOST_BOOST_PRIORITY_LEVEL;
            ObDereferenceObject(process);
        }
    }
}

/* ─── DriverEntry ───────────────────────────────────────────────────────── */

NTSTATUS
DriverEntry(
    _In_ PDRIVER_OBJECT     DriverObject,
    _In_ PUNICODE_STRING    RegistryPath
)
{
    NTSTATUS        status;
    PDEVICE_OBJECT  deviceObject = NULL;
    UNICODE_STRING  deviceName;
    UNICODE_STRING  symLinkName;

    UNREFERENCED_PARAMETER(RegistryPath);

    DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
        "[TopMost] DriverEntry: Initializing TopMost Shield Driver v%d.%d\n",
        TOPMOST_DRIVER_VERSION_MAJOR, TOPMOST_DRIVER_VERSION_MINOR);

    /* Initialize device name and symbolic link */
    RtlInitUnicodeString(&deviceName, TOPMOST_DEVICE_NAME);
    RtlInitUnicodeString(&symLinkName, TOPMOST_SYMLINK_NAME);

    /* Create device object */
    status = IoCreateDevice(
        DriverObject,
        0,                              /* No device extension needed */
        &deviceName,
        FILE_DEVICE_UNKNOWN,
        FILE_DEVICE_SECURE_OPEN,
        FALSE,                          /* Not exclusive */
        &deviceObject
    );

    if (!NT_SUCCESS(status)) {
        DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_ERROR_LEVEL,
            "[TopMost] DriverEntry: IoCreateDevice failed (0x%08X)\n", status);
        return status;
    }

    /* Create symbolic link for user-mode access */
    status = IoCreateSymbolicLink(&symLinkName, &deviceName);
    if (!NT_SUCCESS(status)) {
        DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_ERROR_LEVEL,
            "[TopMost] DriverEntry: IoCreateSymbolicLink failed (0x%08X)\n", status);
        IoDeleteDevice(deviceObject);
        return status;
    }

    /* Set up dispatch routines */
    DriverObject->MajorFunction[IRP_MJ_CREATE]         = TopMostDispatchCreate;
    DriverObject->MajorFunction[IRP_MJ_CLOSE]          = TopMostDispatchClose;
    DriverObject->MajorFunction[IRP_MJ_DEVICE_CONTROL] = TopMostDispatchDeviceControl;
    DriverObject->DriverUnload                         = TopMostDriverUnload;

    /* Use direct I/O for buffer management */
    deviceObject->Flags |= DO_DIRECT_IO;
    deviceObject->Flags &= ~DO_DEVICE_INITIALIZING;

    /* Register process creation callback for monitoring */
    status = PsSetCreateProcessNotifyRoutineEx(
        TopMostProcessNotifyCallback,
        FALSE   /* Register (not remove) */
    );

    if (NT_SUCCESS(status)) {
        g_DriverContext.ProcessCallbackRegistered = TRUE;
        DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
            "[TopMost] DriverEntry: Process notification callback registered\n");
    } else {
        /* Non-fatal: driver works without process monitoring */
        DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_WARNING_LEVEL,
            "[TopMost] DriverEntry: PsSetCreateProcessNotifyRoutineEx failed (0x%08X) - continuing without process monitoring\n",
            status);
    }

    /* Save global state */
    g_DriverContext.DeviceObject = deviceObject;
    g_DriverContext.IsActive     = TRUE;
    g_DriverContext.ProtectedPid = NULL;
    g_DriverContext.BoostCount   = 0;
    g_DriverContext.ObCallbackHandle   = NULL;
    g_DriverContext.ObCallbackRegistered = FALSE;

    /* Register ObRegisterCallbacks for handle-stripping protection */
    {
        OB_OPERATION_REGISTRATION opReg = { 0 };
        OB_CALLBACK_REGISTRATION cbReg = { 0 };
        UNICODE_STRING altitude;

        RtlInitUnicodeString(&altitude, L"321000");

        opReg.ObjectType = PsProcessType;
        opReg.Operations = OB_OPERATION_HANDLE_CREATE | OB_OPERATION_HANDLE_DUPLICATE;
        opReg.PreOperation = TopMostObPreOperationCallback;
        opReg.PostOperation = NULL;

        cbReg.Version = OB_FLT_REGISTRATION_VERSION;
        cbReg.OperationRegistrationCount = 1;
        cbReg.Altitude = altitude;
        cbReg.RegistrationContext = NULL;
        cbReg.OperationRegistration = &opReg;

        status = ObRegisterCallbacks(&cbReg, &g_DriverContext.ObCallbackHandle);
        if (NT_SUCCESS(status)) {
            g_DriverContext.ObCallbackRegistered = TRUE;
            DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
                "[TopMost] DriverEntry: ObRegisterCallbacks registered — process termination protection active\n");
        } else {
            DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_WARNING_LEVEL,
                "[TopMost] DriverEntry: ObRegisterCallbacks failed (0x%08X) — handle protection unavailable\n", status);
        }
    }

    DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
        "[TopMost] DriverEntry: Driver initialized successfully\n");

    return STATUS_SUCCESS;
}

/* ─── Driver Unload ─────────────────────────────────────────────────────── */

VOID
TopMostDriverUnload(
    _In_ PDRIVER_OBJECT DriverObject
)
{
    UNICODE_STRING symLinkName;

    DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
        "[TopMost] DriverUnload: Unloading driver\n");

    /* Unregister process callback */
    if (g_DriverContext.ProcessCallbackRegistered) {
        PsSetCreateProcessNotifyRoutineEx(
            TopMostProcessNotifyCallback,
            TRUE    /* Remove */
        );
        g_DriverContext.ProcessCallbackRegistered = FALSE;
    }

    /* Unregister ObRegisterCallbacks */
    if (g_DriverContext.ObCallbackRegistered && g_DriverContext.ObCallbackHandle) {
        ObUnRegisterCallbacks(g_DriverContext.ObCallbackHandle);
        g_DriverContext.ObCallbackRegistered = FALSE;
        g_DriverContext.ObCallbackHandle = NULL;
        DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
            "[TopMost] DriverUnload: ObRegisterCallbacks unregistered\n");
    }

    /* Delete symbolic link */
    RtlInitUnicodeString(&symLinkName, TOPMOST_SYMLINK_NAME);
    IoDeleteSymbolicLink(&symLinkName);

    /* Delete device object */
    if (DriverObject->DeviceObject != NULL) {
        IoDeleteDevice(DriverObject->DeviceObject);
    }

    g_DriverContext.IsActive = FALSE;

    DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
        "[TopMost] DriverUnload: Driver unloaded successfully\n");
}

/* ─── IRP_MJ_CREATE ─────────────────────────────────────────────────────── */

NTSTATUS
TopMostDispatchCreate(
    _In_ PDEVICE_OBJECT DeviceObject,
    _Inout_ PIRP        Irp
)
{
    UNREFERENCED_PARAMETER(DeviceObject);

    DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
        "[TopMost] DispatchCreate: Device opened by PID %lu\n",
        (ULONG)(ULONG_PTR)PsGetCurrentProcessId());

    Irp->IoStatus.Status      = STATUS_SUCCESS;
    Irp->IoStatus.Information  = 0;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    return STATUS_SUCCESS;
}

/* ─── IRP_MJ_CLOSE ──────────────────────────────────────────────────────── */

NTSTATUS
TopMostDispatchClose(
    _In_ PDEVICE_OBJECT DeviceObject,
    _Inout_ PIRP        Irp
)
{
    UNREFERENCED_PARAMETER(DeviceObject);

    DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
        "[TopMost] DispatchClose: Device closed\n");

    Irp->IoStatus.Status      = STATUS_SUCCESS;
    Irp->IoStatus.Information  = 0;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    return STATUS_SUCCESS;
}

/* ─── IRP_MJ_DEVICE_CONTROL ─────────────────────────────────────────────── */

NTSTATUS
TopMostDispatchDeviceControl(
    _In_ PDEVICE_OBJECT DeviceObject,
    _Inout_ PIRP        Irp
)
{
    NTSTATUS                status = STATUS_SUCCESS;
    PIO_STACK_LOCATION      irpSp;
    ULONG                   ioControlCode;
    ULONG                   outputLength;
    PVOID                   outputBuffer;
    PVOID                   inputBuffer;
    ULONG                   inputLength;
    TOPMOST_STATUS          driverStatus;

    UNREFERENCED_PARAMETER(DeviceObject);

    irpSp           = IoGetCurrentIrpStackLocation(Irp);
    ioControlCode   = irpSp->Parameters.DeviceIoControl.IoControlCode;
    outputLength    = irpSp->Parameters.DeviceIoControl.OutputBufferLength;
    inputLength     = irpSp->Parameters.DeviceIoControl.InputBufferLength;
    inputBuffer     = Irp->AssociatedIrp.SystemBuffer;
    outputBuffer    = Irp->AssociatedIrp.SystemBuffer;

    switch (ioControlCode) {

    /* ── IOCTL_TOPMOST_BOOST_PRIORITY ──────────────────────────────────── */
    case IOCTL_TOPMOST_BOOST_PRIORITY:
    {
        PEPROCESS   callerProcess;
        PETHREAD    callerThread;

        DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
            "[TopMost] IOCTL: BOOST_PRIORITY requested by PID %lu\n",
            (ULONG)(ULONG_PTR)PsGetCurrentProcessId());

        callerThread  = PsGetCurrentThread();
        callerProcess = IoGetRequestorProcess(Irp);

        if (callerThread != NULL) {
            /*
             * KeSetPriorityThread sets the absolute thread scheduling priority.
             * Priority 26 is in the REALTIME range (16-31), making this thread
             * virtually unpreemptable by normal user-mode threads.
             *
             * Priority levels:
             *   1-15:  Variable (normal user-mode range)
             *   16-31: Real-time (kernel and critical threads)
             *   31:    Reserved for zero-page thread
             */
            g_DriverContext.OriginalPriority =
                KeSetPriorityThread((PKTHREAD)callerThread,
                                    TOPMOST_BOOST_PRIORITY_LEVEL);

            DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
                "[TopMost] IOCTL: Thread priority boosted from %d to %d\n",
                (int)g_DriverContext.OriginalPriority,
                TOPMOST_BOOST_PRIORITY_LEVEL);
        }

        /* Record the protected PID */
        g_DriverContext.ProtectedPid = PsGetCurrentProcessId();
        g_DriverContext.BoostCount++;

        /* Return status */
        if (outputLength >= sizeof(TOPMOST_STATUS)) {
            TopMostFillStatus(&driverStatus);
            RtlCopyMemory(outputBuffer, &driverStatus, sizeof(TOPMOST_STATUS));
            Irp->IoStatus.Information = sizeof(TOPMOST_STATUS);
        } else {
            Irp->IoStatus.Information = 0;
        }

        status = STATUS_SUCCESS;
        break;
    }

    /* ── IOCTL_TOPMOST_RESET_PRIORITY ──────────────────────────────────── */
    case IOCTL_TOPMOST_RESET_PRIORITY:
    {
        PETHREAD callerThread = PsGetCurrentThread();

        DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
            "[TopMost] IOCTL: RESET_PRIORITY requested\n");

        if (callerThread != NULL && g_DriverContext.OriginalPriority > 0) {
            KeSetPriorityThread((PKTHREAD)callerThread,
                                g_DriverContext.OriginalPriority);

            DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
                "[TopMost] IOCTL: Thread priority restored to %d\n",
                (int)g_DriverContext.OriginalPriority);
        }

        g_DriverContext.ProtectedPid = NULL;

        /* Return status */
        if (outputLength >= sizeof(TOPMOST_STATUS)) {
            TopMostFillStatus(&driverStatus);
            RtlCopyMemory(outputBuffer, &driverStatus, sizeof(TOPMOST_STATUS));
            Irp->IoStatus.Information = sizeof(TOPMOST_STATUS);
        } else {
            Irp->IoStatus.Information = 0;
        }

        status = STATUS_SUCCESS;
        break;
    }

    /* ── IOCTL_TOPMOST_GET_STATUS ──────────────────────────────────────── */
    case IOCTL_TOPMOST_GET_STATUS:
    {
        DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
            "[TopMost] IOCTL: GET_STATUS requested\n");

        if (outputLength < sizeof(TOPMOST_STATUS)) {
            status = STATUS_BUFFER_TOO_SMALL;
            Irp->IoStatus.Information = sizeof(TOPMOST_STATUS);
            break;
        }

        TopMostFillStatus(&driverStatus);
        RtlCopyMemory(outputBuffer, &driverStatus, sizeof(TOPMOST_STATUS));
        Irp->IoStatus.Information = sizeof(TOPMOST_STATUS);
        status = STATUS_SUCCESS;
        break;
    }

    /* ── IOCTL_TOPMOST_SET_PROTECTED_PID ───────────────────────────────── */
    case IOCTL_TOPMOST_SET_PROTECTED_PID:
    {
        ULONG targetPid;

        DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
            "[TopMost] IOCTL: SET_PROTECTED_PID requested\n");

        if (inputLength < sizeof(ULONG)) {
            status = STATUS_BUFFER_TOO_SMALL;
            Irp->IoStatus.Information = 0;
            break;
        }

        targetPid = *(PULONG)inputBuffer;

        /* Verify the PID exists */
        {
            PEPROCESS targetProcess = NULL;
            status = PsLookupProcessByProcessId(
                (HANDLE)(ULONG_PTR)targetPid, &targetProcess);
            if (!NT_SUCCESS(status)) {
                DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_ERROR_LEVEL,
                    "[TopMost] IOCTL: PID %lu not found\n", targetPid);
                Irp->IoStatus.Information = 0;
                break;
            }
            ObDereferenceObject(targetProcess);
        }

        g_DriverContext.ProtectedPid = (HANDLE)(ULONG_PTR)targetPid;

        DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
            "[TopMost] IOCTL: Protected PID set to %lu\n", targetPid);

        /* Return status */
        if (outputLength >= sizeof(TOPMOST_STATUS)) {
            TopMostFillStatus(&driverStatus);
            RtlCopyMemory(outputBuffer, &driverStatus, sizeof(TOPMOST_STATUS));
            Irp->IoStatus.Information = sizeof(TOPMOST_STATUS);
        } else {
            Irp->IoStatus.Information = 0;
        }

        status = STATUS_SUCCESS;
        break;
    }

    /* ── Unknown IOCTL ─────────────────────────────────────────────────── */
    default:
        DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_WARNING_LEVEL,
            "[TopMost] IOCTL: Unknown control code 0x%08X\n", ioControlCode);
        status = STATUS_INVALID_DEVICE_REQUEST;
        Irp->IoStatus.Information = 0;
        break;
    }

    Irp->IoStatus.Status = status;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    return status;
}

/* ─── Process Notification Callback ─────────────────────────────────────── */

VOID
TopMostProcessNotifyCallback(
    _Inout_  PEPROCESS               Process,
    _In_     HANDLE                  ProcessId,
    _In_opt_ PPS_CREATE_NOTIFY_INFO  CreateInfo
)
{
    UNREFERENCED_PARAMETER(Process);

    if (CreateInfo == NULL) {
        /* Process is exiting */
        if (ProcessId == g_DriverContext.ProtectedPid) {
            DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_WARNING_LEVEL,
                "[TopMost] ProcessNotify: Protected process (PID %lu) terminated!\n",
                (ULONG)(ULONG_PTR)ProcessId);

            g_DriverContext.ProtectedPid = NULL;
            g_DriverContext.IsActive     = FALSE;
        }
    } else {
        /* Process is being created - log for monitoring */
        if (g_DriverContext.ProtectedPid != NULL) {
            DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_TRACE_LEVEL,
                "[TopMost] ProcessNotify: New process PID %lu created (ImageFileName: %wZ)\n",
                (ULONG)(ULONG_PTR)ProcessId,
                CreateInfo->ImageFileName);
        }
    }
}

/* ─── Object Callback: Strip PROCESS_TERMINATE from handle operations ──── */

OB_PREOP_CALLBACK_STATUS
TopMostObPreOperationCallback(
    _In_ PVOID                          RegistrationContext,
    _Inout_ POB_PRE_OPERATION_INFORMATION OperationInformation
)
{
    UNREFERENCED_PARAMETER(RegistrationContext);

    /* Only protect process handles */
    if (OperationInformation->ObjectType != *PsProcessType)
        return OB_PREOP_SUCCESS;

    /* Only act if we have a protected PID */
    if (g_DriverContext.ProtectedPid == NULL)
        return OB_PREOP_SUCCESS;

    /* Check if the target process is our protected process */
    {
        PEPROCESS targetProcess = (PEPROCESS)OperationInformation->Object;
        HANDLE targetPid = PsGetProcessId(targetProcess);
        HANDLE callerPid = PsGetCurrentProcessId();

        if (targetPid != g_DriverContext.ProtectedPid)
            return OB_PREOP_SUCCESS;

        /* Allow the protected process to terminate itself (for clean exit) */
        if (callerPid == g_DriverContext.ProtectedPid)
            return OB_PREOP_SUCCESS;

        /* Allow kernel-mode callers (e.g., csrss.exe cleanup) */
        if (OperationInformation->KernelHandle)
            return OB_PREOP_SUCCESS;

        /* Strip dangerous access rights from the handle */
        if (OperationInformation->Operation == OB_OPERATION_HANDLE_CREATE) {
            OperationInformation->Parameters->CreateHandleInformation.DesiredAccess
                &= ~(PROCESS_TERMINATE | PROCESS_SUSPEND_RESUME);
        }
        else if (OperationInformation->Operation == OB_OPERATION_HANDLE_DUPLICATE) {
            OperationInformation->Parameters->DuplicateHandleInformation.DesiredAccess
                &= ~(PROCESS_TERMINATE | PROCESS_SUSPEND_RESUME);
        }

        DbgPrintEx(DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
            "[TopMost] ObCallback: Stripped TERMINATE from PID %lu targeting protected PID %lu\n",
            (ULONG)(ULONG_PTR)callerPid,
            (ULONG)(ULONG_PTR)targetPid);
    }

    return OB_PREOP_SUCCESS;
}
