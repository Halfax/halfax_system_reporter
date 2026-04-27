// GUID definition TU for Halfax Telemetry device interface
// Keep INITGUID scoped here and avoid including winioctl to prevent redefining system GUIDs
#define INITGUID
#include <guiddef.h>

// {8E6F1D3A-47B2-4E9C-8D7A-9F2B4C5E6A7D}
DEFINE_GUID(GUID_DEVINTERFACE_HALFAX_TELEMETRY,
	0x8e6f1d3a, 0x47b2, 0x4e9c, 0x8d, 0x7a, 0x9f, 0x2b, 0x4c, 0x5e, 0x6a, 0x7d);
