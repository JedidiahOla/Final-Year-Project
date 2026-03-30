#ifndef SENSORS_H
#define SENSORS_H

#include <Arduino.h>

// Sensor reading and control
// Turbidity + TDS via ADS1115, temperature via DS18B20, battery on internal ADC
// Sensors powered through 2N7000 MOSFET - call sensorsOn()/sensorsOff()

struct SensorReading {
    float turbidity_ntu;
    int   turbidity_raw;    // raw ADS1115 count, kept for recalibration later
    float tds_mgl;
    float temperature_c;
    int   battery_mv;
    uint8_t fault_flags;
    bool  tank_dry;
};

void sensorsInit();
void sensorsOn();
void sensorsOff();

SensorReading readAllSensors();

// Individual sensor functions (for testing/calibration)
int   readTurbidityRaw();
float readTurbidityFromRaw(int raw);
float readTurbidity();
float readTDS(float temperature_c);
float readTemperature();
int   readBatteryMv();

// Returns season index from month (1-12)
// 0=Dry(Nov-Apr), 1=PreMonsoon(May-Jun), 2=Monsoon(Jul-Sep), 3=PostMonsoon(Oct)
int getSeasonIndex(int month);

#endif
