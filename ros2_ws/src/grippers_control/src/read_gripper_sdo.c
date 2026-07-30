#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include "ethercat.h"

static char IOmap[4096];

static void read_u16(int slave, uint16 index, uint8 subindex, const char *name)
{
    uint16 value = 0;
    int size = sizeof(value);

    int wkc = ec_SDOread(
        slave,
        index,
        subindex,
        FALSE,
        &size,
        &value,
        EC_TIMEOUTRXM
    );

    if (wkc > 0)
    {
        printf("%s (0x%04X:%02X) = %u", name, index, subindex, value);

        if (subindex >= 13 && subindex <= 18)
        {
            printf(" = %.1f mm", value / 10.0);
        }

        printf("\n");
    }
    else
    {
        printf("Failed to read %s (0x%04X:%02X)\n",
               name, index, subindex);
    }
}

static void read_u32(int slave,
                     uint16 index,
                     uint8 subindex,
                     const char *name)
{
    uint32 value = 0;
    int size = sizeof(value);

    int wkc = ec_SDOread(
        slave,
        index,
        subindex,
        FALSE,
        &size,
        &value,
        EC_TIMEOUTRXM
    );

    if (wkc > 0)
    {
        printf("%s (0x%04X:%02X) = %u (0x%08X)\n",
               name,
               index,
               subindex,
               value,
               value);
    }
    else
    {
        printf("Failed to read %s (0x%04X:%02X)\n",
               name,
               index,
               subindex);
    }
}

int main(int argc, char *argv[])
{
    if (argc != 3)
    {
        printf("Usage: sudo %s <interface> <slave_index>\n", argv[0]);
        return 1;
    }

    int slave = atoi(argv[2]);

    if (!ec_init(argv[1]))
    {
        printf("Failed to open interface %s\n", argv[1]);
        return 1;
    }

    if (ec_config_init(FALSE) <= 0)
    {
        printf("No EtherCAT slaves found\n");
        ec_close();
        return 1;
    }

    printf("Slave %d: %s\n", slave, ec_slave[slave].name);

    read_u32(slave, 0x1018, 1, "Vendor ID");
    read_u32(slave, 0x1018, 2, "Product Code");
    read_u32(slave, 0x1018, 3, "Revision");
    read_u32(slave, 0x1018, 4, "Serial Number");
    read_u16(slave, 0x8000, 9,  "CloseSpeed");
    read_u16(slave, 0x8000, 10, "OpenSpeed");
    read_u16(slave, 0x8000, 11, "CloseTorque");
    read_u16(slave, 0x8000, 13, "CloseWidth");
    read_u16(slave, 0x8000, 14, "OpenWidth");
    read_u16(slave, 0x8000, 17, "MaxFingerWidth");
    read_u16(slave, 0x8000, 18, "MinFingerWidth");
    read_u16(slave, 0x8000, 19, "AppVersion");  
    read_u16(slave, 0x8000, 20, "EcatVersion");

    ec_close();
    return 0;
}
