#include <iostream>
#include <thread>
#include <chrono>
#include <random>
#include <cmath>

#ifdef USE_CONNEXT
#include <ndds/ndds_cpp.h>
#include "ShipThreat.h"
#include "ShipThreatSupport.h"
#endif

#if defined(__has_include)
#  if __has_include("ShipThreat.h")
#    include "ShipThreat.h"
#  else
namespace ship {
    struct Threat { int id; double x,y,heading,speed; int severity; };
    struct SensorDetection { int sensor_id; int threat_id; double x,y; int confidence; };
}
#  endif
#else
namespace ship {
    struct Threat { int id; double x,y,heading,speed; int severity; };
    struct SensorDetection { int sensor_id; int threat_id; double x,y; int confidence; };
}
#endif

using namespace std::chrono_literals;

#ifdef USE_CONNEXT
static ship::SensorDetectionDataWriter *g_detection_writer = nullptr;

// Ship position (pixels) — must match command_control constants
static const float SHIP_X_PX = 400.0f;
static const float SHIP_Y_PX = 570.0f;
// Scale: 350 miles = 570 px  =>  1 nm = 1.1508 mi × (570/350) px/mi ≈ 1.875 px/nm

// Aegis destroyer sensor suite
// range_px: detection radius from ship in screen pixels
struct SensorDef { int id; const char* name; int conf_min, conf_max; float range_px; };
static const SensorDef SENSOR_DEFS[] = {
    {1, "AN/SPY-1D",  88, 100, 412.0f},  // 220 nm — primary Aegis phased-array radar
    {2, "AN/SPQ-9B",  72,  90,  75.0f},  //  40 nm — horizon search / gun FC radar
    {3, "AN/SPS-67",  55,  75,  47.0f},  //  25 nm — surface search radar
    {4, "AN/SLQ-32",  65,  85, 187.0f},  // 100 nm — electronic warfare / ESM
};

class ThreatListener : public DDSDataReaderListener {
public:
    std::mt19937 rng{(unsigned)std::chrono::system_clock::now().time_since_epoch().count()};
    void on_data_available(DDSDataReader* reader) override {
        ship::ThreatDataReader *tr = ship::ThreatDataReader::narrow(reader);
        if (!tr) return;
        ship::ThreatSeq seq;
        DDS_SampleInfoSeq infos;
        DDS_ReturnCode_t ret = tr->take(seq, infos, DDS_LENGTH_UNLIMITED,
                                        DDS_ANY_SAMPLE_STATE, DDS_ANY_VIEW_STATE, DDS_ANY_INSTANCE_STATE);
        if (ret == DDS_RETCODE_OK) {
            for (DDS_Long i = 0; i < seq.length(); ++i) {
                // Each sensor in the suite reports a detection
                for (const auto& s : SENSOR_DEFS) {
                    // Only report when threat is within this sensor's detection range
                    float dx = float(seq[i].x) - SHIP_X_PX;
                    float dy = float(seq[i].y) - SHIP_Y_PX;
                    if (sqrtf(dx*dx + dy*dy) > s.range_px) continue;

                    std::uniform_int_distribution<int> conf_dist(s.conf_min, s.conf_max);
                    ship::SensorDetection d;
                    d.sensor_id  = s.id;
                    d.threat_id  = seq[i].id;
                    d.x          = seq[i].x;
                    d.y          = seq[i].y;
                    d.confidence = conf_dist(rng);
                    if (g_detection_writer) g_detection_writer->write(d, DDS_HANDLE_NIL);
                }
            }
        }
        if (ret == DDS_RETCODE_OK)
            tr->return_loan(seq, infos);
    }
};
#endif

void publishDetection(const ship::SensorDetection &d)
{
#ifdef USE_CONNEXT
    if (g_detection_writer) {
        g_detection_writer->write(d, DDS_HANDLE_NIL);
        return;
    }
#endif
    // Placeholder for DDS publish
    std::cout << "[SENSOR] sensor=" << d.sensor_id << " detected threat=" << d.threat_id << " at (" << d.x << "," << d.y << ") conf=" << d.confidence << "\n";
}

int main()
{
#ifdef USE_CONNEXT
    // DDS setup: subscribe to ThreatTopic and publish SensorDetectionTopic
    DDSDomainParticipant *participant = DDSDomainParticipantFactory::get_instance()->create_participant(
        0, DDS_PARTICIPANT_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
    if (!participant) { std::cerr << "DDS create_participant failed" << std::endl; }
    else {
        ship::ThreatTypeSupport::register_type(participant, ship::ThreatTypeSupport::get_type_name());
        ship::SensorDetectionTypeSupport::register_type(participant, ship::SensorDetectionTypeSupport::get_type_name());

        DDSTopic *threat_topic = participant->create_topic("ThreatTopic", ship::ThreatTypeSupport::get_type_name(), DDS_TOPIC_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
        DDSTopic *sensor_topic = participant->create_topic("SensorDetectionTopic", ship::SensorDetectionTypeSupport::get_type_name(), DDS_TOPIC_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);

        DDSPublisher *publisher = participant->create_publisher(DDS_PUBLISHER_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
        DDSDataWriter *dw = publisher->create_datawriter(sensor_topic, DDS_DATAWRITER_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
        g_detection_writer = ship::SensorDetectionDataWriter::narrow(dw);

        DDSSubscriber *subscriber = participant->create_subscriber(DDS_SUBSCRIBER_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
        static ThreatListener tl;
        DDSDataReader *th_dr = subscriber->create_datareader(threat_topic, DDS_DATAREADER_QOS_DEFAULT, &tl, DDS_DATA_AVAILABLE_STATUS);
    }
#else
    std::cout << "Sensor app starting (no DDS enabled by default)." << std::endl;
#endif

    std::mt19937 rng((unsigned)std::chrono::system_clock::now().time_since_epoch().count());
    std::uniform_real_distribution<double> pos(-1000.0,1000.0);

    int sensor_id = 1;
    while (true) {
        // Simulate periodic detection broadcasts when no DDS
#ifndef USE_CONNEXT
        ship::SensorDetection d;
        d.sensor_id = sensor_id;
        d.threat_id = (rng() % 20) + 1;
        d.x = pos(rng);
        d.y = pos(rng);
        d.confidence = 50 + (rng() % 50);
        publishDetection(d);
        std::this_thread::sleep_for(2s);
#else
        std::this_thread::sleep_for(2s);
#endif
    }
    return 0;
}
