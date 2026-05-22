#include <iostream>
#include <thread>
#include <chrono>
#include <random>
#include <set>
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
    struct EffectorAction { int effector_id; int threat_id; bool destroyed; double x,y; };
}
#  endif
#else
namespace ship {
    struct Threat { int id; double x,y,heading,speed; int severity; };
    struct EffectorAction { int effector_id; int threat_id; bool destroyed; double x,y; };
}
#endif

using namespace std::chrono_literals;

#ifdef USE_CONNEXT
static ship::EffectorActionDataWriter *g_action_writer = nullptr;

// Aegis destroyer weapon systems with individual probability-of-kill (%)
struct EffectorDef { int id; const char* name; int pk; };
static const EffectorDef EFFECTOR_DEFS[] = {
    {1, "SM-2 MR",   75},  // Standard Missile 2 Medium Range (VLS)
    {2, "SM-6",      87},  // Standard Missile 6 extended range (VLS)
    {3, "ESSM",      68},  // Evolved Sea Sparrow Missile (VLS)
    {4, "CIWS",      52},  // Phalanx Close-In Weapon System
    {5, "MK 45/62",  36},  // 5-inch/62 cal gun (surface/low-alt threats)
};

class ThreatListener : public DDSDataReaderListener {
public:
    std::mt19937 rng{(unsigned)std::chrono::system_clock::now().time_since_epoch().count()};
    std::uniform_int_distribution<int> chance{1, 100};
    std::set<int> engaged;   // threat IDs already engaged — skip republished updates
    void on_data_available(DDSDataReader* reader) override {
        ship::ThreatDataReader *tr = ship::ThreatDataReader::narrow(reader);
        if (!tr) return;
        ship::ThreatSeq seq;
        DDS_SampleInfoSeq infos;
        DDS_ReturnCode_t ret = tr->take(seq, infos, DDS_LENGTH_UNLIMITED,
                                        DDS_ANY_SAMPLE_STATE, DDS_ANY_VIEW_STATE, DDS_ANY_INSTANCE_STATE);
        if (ret == DDS_RETCODE_OK) {
            for (DDS_Long i = 0; i < seq.length(); ++i) {
                // Only engage when threat has entered SPY-1D detection range
                // (same 412 px radius used by the sensor — detect first, then shoot)
                {
                    float dx = float(seq[i].x) - 400.0f;  // SHIP_X
                    float dy = float(seq[i].y) - 570.0f;  // SHIP_Y
                    if (sqrtf(dx*dx + dy*dy) > 380.0f) continue;  // not yet in range
                }
                if (engaged.count(seq[i].id)) continue;  // already engaged this threat
                engaged.insert(seq[i].id);
                // Layered defense: all weapons engage; MK45 only for surface threats
                for (const auto& e : EFFECTOR_DEFS) {
                    if (e.id == 5 && seq[i].severity < 3) continue; // MK45 for surface threats only
                    ship::EffectorAction a;
                    a.effector_id = e.id;
                    a.threat_id   = seq[i].id;
                    a.destroyed   = (chance(rng) <= e.pk);
                    a.x           = seq[i].x;
                    a.y           = seq[i].y;
                    if (g_action_writer) g_action_writer->write(a, DDS_HANDLE_NIL);
                }
            }
        }
        if (ret == DDS_RETCODE_OK)
            tr->return_loan(seq, infos);
    }
};
#endif

void publishAction(const ship::EffectorAction &a)
{
#ifdef USE_CONNEXT
    if (g_action_writer) {
        g_action_writer->write(a, DDS_HANDLE_NIL);
        return;
    }
#endif
    // Placeholder for DDS publish
    std::cout << "[EFFECTOR] effector=" << a.effector_id << " action on threat=" << a.threat_id << " destroyed=" << a.destroyed << "\n";
}

int main()
{
#ifdef USE_CONNEXT
    // DDS setup: subscribe to ThreatTopic and publish EffectorActionTopic
    DDSDomainParticipant *participant = DDSDomainParticipantFactory::get_instance()->create_participant(
        0, DDS_PARTICIPANT_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
    if (!participant) { std::cerr << "DDS create_participant failed" << std::endl; }
    else {
        ship::ThreatTypeSupport::register_type(participant, ship::ThreatTypeSupport::get_type_name());
        ship::EffectorActionTypeSupport::register_type(participant, ship::EffectorActionTypeSupport::get_type_name());

        DDSTopic *threat_topic = participant->create_topic("ThreatTopic", ship::ThreatTypeSupport::get_type_name(), DDS_TOPIC_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
        DDSTopic *effector_topic = participant->create_topic("EffectorActionTopic", ship::EffectorActionTypeSupport::get_type_name(), DDS_TOPIC_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);

        DDSPublisher *publisher = participant->create_publisher(DDS_PUBLISHER_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
        DDSDataWriter *dw = publisher->create_datawriter(effector_topic, DDS_DATAWRITER_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
        g_action_writer = ship::EffectorActionDataWriter::narrow(dw);

        DDSSubscriber *subscriber = participant->create_subscriber(DDS_SUBSCRIBER_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
        static ThreatListener tl;
        DDSDataReader *th_dr = subscriber->create_datareader(threat_topic, DDS_DATAREADER_QOS_DEFAULT, &tl, DDS_DATA_AVAILABLE_STATUS);
    }
#else
    std::cout << "Effector app starting (no DDS enabled by default)." << std::endl;
#endif

    std::mt19937 rng((unsigned)std::chrono::system_clock::now().time_since_epoch().count());
    int effector_id = 1;
    while (true) {
#ifndef USE_CONNEXT
        ship::EffectorAction a;
        a.effector_id = effector_id;
        a.threat_id = (rng() % 20) + 1;
        a.destroyed = (rng() % 2) == 0;
        a.x = 0.0; a.y = 0.0;
        publishAction(a);
        std::this_thread::sleep_for(3s);
#else
        std::this_thread::sleep_for(3s);
#endif
    }
    return 0;
}
