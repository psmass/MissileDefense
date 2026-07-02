#include <SDL.h>
#include <SDL_image.h>
#include <iostream>
#include <vector>
#include <map>
#include <chrono>
#include <thread>
#include <mutex>
#include <cstdint>
#include <cstdio>
#include <cmath>
#include <random>
#include <set>

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
    struct EffectorAction { int effector_id; int threat_id; bool destroyed; double x,y; };
}
#  endif
#else
// Fallback types
namespace ship {
    struct Threat { int id; double x,y,heading,speed; int severity; };
    struct SensorDetection { int sensor_id; int threat_id; double x,y; int confidence; };
    struct EffectorAction { int effector_id; int threat_id; bool destroyed; double x,y; };
}
#endif

using namespace std::chrono_literals;

// ============================================================
// Embedded 5x7 bitmap font (Adafruit GFX glcdfont, BSD licensed)
// ASCII 32-126.  Each entry: 5 column bytes.  Bit 0 = top row.
// ============================================================
static const uint8_t font5x7[95][5] = {
    {0x00,0x00,0x00,0x00,0x00}, // ' '
    {0x00,0x00,0x5F,0x00,0x00}, // '!'
    {0x00,0x07,0x00,0x07,0x00}, // '"'
    {0x14,0x7F,0x14,0x7F,0x14}, // '#'
    {0x24,0x2A,0x7F,0x2A,0x12}, // '$'
    {0x23,0x13,0x08,0x64,0x62}, // '%'
    {0x36,0x49,0x55,0x22,0x50}, // '&'
    {0x00,0x05,0x03,0x00,0x00}, // '\''
    {0x00,0x1C,0x22,0x41,0x00}, // '('
    {0x00,0x41,0x22,0x1C,0x00}, // ')'
    {0x08,0x2A,0x1C,0x2A,0x08}, // '*'
    {0x08,0x08,0x3E,0x08,0x08}, // '+'
    {0x00,0x50,0x30,0x00,0x00}, // ','
    {0x08,0x08,0x08,0x08,0x08}, // '-'
    {0x00,0x60,0x60,0x00,0x00}, // '.'
    {0x20,0x10,0x08,0x04,0x02}, // '/'
    {0x3E,0x51,0x49,0x45,0x3E}, // '0'
    {0x00,0x42,0x7F,0x40,0x00}, // '1'
    {0x42,0x61,0x51,0x49,0x46}, // '2'
    {0x21,0x41,0x45,0x4B,0x31}, // '3'
    {0x18,0x14,0x12,0x7F,0x10}, // '4'
    {0x27,0x45,0x45,0x45,0x39}, // '5'
    {0x3C,0x4A,0x49,0x49,0x30}, // '6'
    {0x01,0x71,0x09,0x05,0x03}, // '7'
    {0x36,0x49,0x49,0x49,0x36}, // '8'
    {0x06,0x49,0x49,0x29,0x1E}, // '9'
    {0x00,0x36,0x36,0x00,0x00}, // ':'
    {0x00,0x56,0x36,0x00,0x00}, // ';'
    {0x00,0x08,0x14,0x22,0x41}, // '<'
    {0x14,0x14,0x14,0x14,0x14}, // '='
    {0x41,0x22,0x14,0x08,0x00}, // '>'
    {0x02,0x01,0x51,0x09,0x06}, // '?'
    {0x32,0x49,0x79,0x41,0x3E}, // '@'
    {0x7E,0x11,0x11,0x11,0x7E}, // 'A'
    {0x7F,0x49,0x49,0x49,0x36}, // 'B'
    {0x3E,0x41,0x41,0x41,0x22}, // 'C'
    {0x7F,0x41,0x41,0x22,0x1C}, // 'D'
    {0x7F,0x49,0x49,0x49,0x41}, // 'E'
    {0x7F,0x09,0x09,0x01,0x01}, // 'F'
    {0x3E,0x41,0x41,0x51,0x32}, // 'G'
    {0x7F,0x08,0x08,0x08,0x7F}, // 'H'
    {0x00,0x41,0x7F,0x41,0x00}, // 'I'
    {0x20,0x40,0x41,0x3F,0x01}, // 'J'
    {0x7F,0x08,0x14,0x22,0x41}, // 'K'
    {0x7F,0x40,0x40,0x40,0x40}, // 'L'
    {0x7F,0x02,0x04,0x02,0x7F}, // 'M'
    {0x7F,0x04,0x08,0x10,0x7F}, // 'N'
    {0x3E,0x41,0x41,0x41,0x3E}, // 'O'
    {0x7F,0x09,0x09,0x09,0x06}, // 'P'
    {0x3E,0x41,0x51,0x21,0x5E}, // 'Q'
    {0x7F,0x09,0x19,0x29,0x46}, // 'R'
    {0x46,0x49,0x49,0x49,0x31}, // 'S'
    {0x01,0x01,0x7F,0x01,0x01}, // 'T'
    {0x3F,0x40,0x40,0x40,0x3F}, // 'U'
    {0x1F,0x20,0x40,0x20,0x1F}, // 'V'
    {0x7F,0x20,0x18,0x20,0x7F}, // 'W'
    {0x63,0x14,0x08,0x14,0x63}, // 'X'
    {0x03,0x04,0x78,0x04,0x03}, // 'Y'
    {0x61,0x51,0x49,0x45,0x43}, // 'Z'
    {0x00,0x00,0x7F,0x41,0x41}, // '['
    {0x02,0x04,0x08,0x10,0x20}, // '\'
    {0x41,0x41,0x7F,0x00,0x00}, // ']'
    {0x04,0x02,0x01,0x02,0x04}, // '^'
    {0x40,0x40,0x40,0x40,0x40}, // '_'
    {0x00,0x01,0x02,0x04,0x00}, // '`'
    {0x20,0x54,0x54,0x54,0x78}, // 'a'
    {0x7F,0x48,0x44,0x44,0x38}, // 'b'
    {0x38,0x44,0x44,0x44,0x20}, // 'c'
    {0x38,0x44,0x44,0x48,0x7F}, // 'd'
    {0x38,0x54,0x54,0x54,0x18}, // 'e'
    {0x08,0x7E,0x09,0x01,0x02}, // 'f'
    {0x08,0x54,0x54,0x54,0x3C}, // 'g'
    {0x7F,0x08,0x04,0x04,0x78}, // 'h'
    {0x00,0x44,0x7D,0x40,0x00}, // 'i'
    {0x20,0x40,0x44,0x3D,0x00}, // 'j'
    {0x00,0x7F,0x10,0x28,0x44}, // 'k'
    {0x00,0x41,0x7F,0x40,0x00}, // 'l'
    {0x7C,0x04,0x18,0x04,0x78}, // 'm'
    {0x7C,0x08,0x04,0x04,0x78}, // 'n'
    {0x38,0x44,0x44,0x44,0x38}, // 'o'
    {0x7C,0x14,0x14,0x14,0x08}, // 'p'
    {0x08,0x14,0x14,0x18,0x7C}, // 'q'
    {0x7C,0x08,0x04,0x04,0x08}, // 'r'
    {0x48,0x54,0x54,0x54,0x20}, // 's'
    {0x04,0x3F,0x44,0x40,0x20}, // 't'
    {0x3C,0x40,0x40,0x20,0x7C}, // 'u'
    {0x1C,0x20,0x40,0x20,0x1C}, // 'v'
    {0x3C,0x40,0x30,0x40,0x3C}, // 'w'
    {0x44,0x28,0x10,0x28,0x44}, // 'x'
    {0x0C,0x50,0x50,0x50,0x3C}, // 'y'
    {0x44,0x64,0x54,0x4C,0x44}, // 'z'
    {0x00,0x08,0x36,0x41,0x00}, // '{'
    {0x00,0x00,0x7F,0x00,0x00}, // '|'
    {0x00,0x41,0x36,0x08,0x00}, // '}'
    {0x08,0x08,0x2A,0x1C,0x08}, // '~'
};

static void draw_char(SDL_Renderer* ren, int x, int y, char c, int scale = 1) {
    if (c < 32 || c > 126) return;
    const uint8_t* g = font5x7[(unsigned char)c - 32];
    for (int col = 0; col < 5; col++) {
        for (int row = 0; row < 7; row++) {
            if (g[col] & (1 << row)) {
                SDL_Rect px = {x + col * scale, y + row * scale, scale, scale};
                SDL_RenderFillRect(ren, &px);
            }
        }
    }
}

static void draw_text(SDL_Renderer* ren, int x, int y, const char* s, int scale = 1) {
    for (int i = 0; s[i]; i++)
        draw_char(ren, x + i * 6 * scale, y, s[i], scale);
}

// 9-character fixed-width name lookups for Aegis sensor/weapon systems
static const char* sensor_name(int id) {
    switch (id) {
        case 1: return "AN/SPY-1D";   // Primary Aegis phased-array radar
        case 2: return "AN/SPQ-9B";   // Horizon Search Radar
        case 3: return "AN/SPS-67";   // Surface Search Radar
        case 4: return "AN/SLQ-32";   // Electronic Warfare System
        default: return "SENSOR   ";
    }
}
static const char* effector_name(int id) {
    switch (id) {
        case 1: return "SM-2 MR  ";   // Standard Missile 2 Medium Range
        case 2: return "SM-6     ";   // Standard Missile 6
        case 3: return "ESSM     ";   // Evolved Sea Sparrow Missile
        case 4: return "CIWS     ";   // Phalanx Close-In Weapon System
        case 5: return "MK 45/62 ";   // 5-inch/62 cal gun
        default: return "EFFECTOR ";
    }
}

// ============================================================
// Ship constants, visual-effect structs, and draw helpers
// ============================================================
static const int SHIP_X = 400;
static const int SHIP_Y = 570;  // waterline y position (side view)

struct LaunchPlume { float x, y, age, life; };
struct KillBlast   { float x, y, age, life; };
struct Interceptor { float x, y; int target_id; float speed, age, life; bool will_kill, done; };

// Draw typed threat shape; angle = atan2 direction of travel toward ship
static void draw_threat(SDL_Renderer* ren, int x, int y, float angle, int type) {
    float ca = cosf(angle), sa = sinf(angle);
    auto pt = [&](float fwd, float rt) -> SDL_Point {
        return { x + int(ca*fwd - sa*rt), y + int(sa*fwd + ca*rt) };
    };
    if (type == 0) {
        // Ballistic missile: elongated body + tail fins
        SDL_SetRenderDrawColor(ren, 255, 80, 30, 255);
        SDL_Point tip  = pt( 9, 0);
        SDL_Point body = pt(-5, 0);
        SDL_Point fl   = pt(-5, 5);
        SDL_Point fr   = pt(-5,-5);
        SDL_Point n2   = pt( 7, 2), n3 = pt( 7,-2);
        SDL_RenderDrawLine(ren, tip.x,  tip.y,  body.x, body.y);
        SDL_RenderDrawLine(ren, body.x, body.y, fl.x,   fl.y  );
        SDL_RenderDrawLine(ren, body.x, body.y, fr.x,   fr.y  );
        SDL_RenderDrawLine(ren, n2.x,   n2.y,   tip.x,  tip.y );
        SDL_RenderDrawLine(ren, n3.x,   n3.y,   tip.x,  tip.y );
    } else if (type == 1) {
        // Drone / UAS: X-frame with rotor blobs
        SDL_SetRenderDrawColor(ren, 180, 40, 210, 255);
        for (int arm = 0; arm < 4; arm++) {
            float aa = arm * 3.14159f / 2.0f + 3.14159f / 4.0f;
            SDL_Point tip2 = { x + int(cosf(aa)*8), y + int(sinf(aa)*8) };
            SDL_RenderDrawLine(ren, x, y, tip2.x, tip2.y);
            SDL_Rect dot = { tip2.x - 2, tip2.y - 2, 4, 4 };
            SDL_RenderFillRect(ren, &dot);
        }
        SDL_Rect body2 = { x - 2, y - 2, 4, 4 };
        SDL_RenderFillRect(ren, &body2);
    } else {
        // Anti-ship cruise missile: swept delta wing
        SDL_SetRenderDrawColor(ren, 255, 50, 50, 255);
        SDL_Point tip  = pt( 9, 0);
        SDL_Point wl   = pt(-5, 8);
        SDL_Point wr   = pt(-5,-8);
        SDL_Point tail = pt(-7, 0);
        SDL_RenderDrawLine(ren, tip.x, tip.y, wl.x, wl.y);
        SDL_RenderDrawLine(ren, tip.x, tip.y, wr.x, wr.y);
        SDL_RenderDrawLine(ren, wl.x, wl.y, tail.x, tail.y);
        SDL_RenderDrawLine(ren, wr.x, wr.y, tail.x, tail.y);
    }
}

// Draw Arleigh Burke-class destroyer side profile
// Bow faces RIGHT, stern faces LEFT  |  cx = hull centre-x, cy = waterline
static void draw_destroyer(SDL_Renderer* ren, int cx, int cy) {
    const int SL  = cx - 118;  // stern left  edge
    const int BR  = cx + 118;  // bow   right edge  (hull body ends here)
    const int DK  = cy - 16;   // main deck
    const int FDK = DK - 6;    // raised forecastle
    const int BK  = cy + 9;    // keel

    // -- below-waterline hull (dark charcoal) --
    SDL_SetRenderDrawColor(ren, 50, 58, 66, 255);
    for (int iy = cy; iy <= BK; iy++) {
        float t  = float(iy - cy) / float(BK - cy);
        int   lx = SL + 6 + int(4 * t);
        int   rx = BR - 4 - int(4 * t);
        SDL_RenderDrawLine(ren, lx, iy, rx, iy);
    }

    // -- main hull above waterline (light grey) --
    SDL_SetRenderDrawColor(ren, 128, 138, 148, 255);
    SDL_Rect hull = {SL + 4, DK, BR - SL - 12, cy - DK};
    SDL_RenderFillRect(ren, &hull);

    // -- raked bow (scan-fill triangle, bow on right) --
    for (int iy = DK; iy <= BK; iy++) {
        float t  = float(iy - DK) / float(BK - DK);
        // peak at waterline, taper top and bottom
        int tip = BR - 2 + int(14.0f * sinf(t * 3.14159f));
        SDL_RenderDrawLine(ren, BR - 12, iy, tip, iy);
    }

    // -- stern (vertical with slight rake) --
    SDL_Rect stern_fill = {SL, DK, 8, BK - DK};
    SDL_RenderFillRect(ren, &stern_fill);

    // -- prominent tan/khaki weather-deck stripe (visible in real ship photos) --
    SDL_SetRenderDrawColor(ren, 162, 148, 98, 255);
    SDL_Rect deck_stripe = {SL + 4, DK, BR - SL - 12, 3};
    SDL_RenderFillRect(ren, &deck_stripe);

    // -- raised forecastle (forward, right half of ship) --
    SDL_SetRenderDrawColor(ren, 120, 130, 140, 255);
    SDL_Rect fc = {cx + 8, FDK, BR - cx - 20, DK - FDK};
    SDL_RenderFillRect(ren, &fc);
    SDL_SetRenderDrawColor(ren, 155, 142, 94, 255);
    SDL_Rect fc_stripe = {cx + 8, FDK, BR - cx - 20, 2};
    SDL_RenderFillRect(ren, &fc_stripe);

    // -- Mk45 5"/62 gun mount (on forecastle, near bow) --
    SDL_SetRenderDrawColor(ren, 105, 112, 122, 255);
    SDL_Rect gun_base = {cx + 80, FDK - 8, 18, 8};
    SDL_RenderFillRect(ren, &gun_base);
    SDL_SetRenderDrawColor(ren, 88, 95, 104, 255);
    SDL_RenderDrawLine(ren, cx + 80, FDK - 5, cx + 102, FDK - 5);
    SDL_RenderDrawLine(ren, cx + 80, FDK - 4, cx + 102, FDK - 4);

    // -- VLS forward cells (Mark 41, forecastle) --
    SDL_SetRenderDrawColor(ren, 110, 118, 128, 255);
    SDL_Rect vls_f = {cx + 20, FDK - 4, 50, 4};
    SDL_RenderFillRect(ren, &vls_f);
    SDL_SetRenderDrawColor(ren, 85, 92, 102, 255);
    for (int v = 1; v < 6; v++)
        SDL_RenderDrawLine(ren, cx+20+v*8, FDK-4, cx+20+v*8, FDK);

    // -- forward superstructure base (wide, at main-deck level) --
    SDL_SetRenderDrawColor(ren, 142, 152, 162, 255);
    SDL_Rect fwd_lo = {cx - 18, FDK, 38, DK - FDK};
    SDL_RenderFillRect(ren, &fwd_lo);
    SDL_Rect fwd_mid = {cx - 14, DK - 32, 32, 32 - (DK - FDK)};
    SDL_RenderFillRect(ren, &fwd_mid);

    // -- bridge level (stepped inward) --
    SDL_SetRenderDrawColor(ren, 150, 160, 170, 255);
    SDL_Rect bridge = {cx - 10, DK - 44, 26, 13};
    SDL_RenderFillRect(ren, &bridge);
    // bridge windows
    SDL_SetRenderDrawColor(ren, 45, 68, 95, 255);
    SDL_Rect wins = {cx - 9, DK - 43, 24, 4};
    SDL_RenderFillRect(ren, &wins);

    // -- SPY-1D phased array radar panel (flat rectangle, on mast face) --
    SDL_SetRenderDrawColor(ren, 118, 126, 136, 255);
    SDL_Rect spy = {cx - 12, DK - 57, 22, 15};
    SDL_RenderFillRect(ren, &spy);
    // panel divider lines
    SDL_SetRenderDrawColor(ren, 95, 102, 112, 255);
    SDL_RenderDrawLine(ren, cx - 1, DK - 57, cx - 1, DK - 42);
    SDL_RenderDrawLine(ren, cx - 12, DK - 49, cx + 10, DK - 49);

    // -- foremast (twin poles + yardarms + stays) --
    SDL_SetRenderDrawColor(ren, 168, 174, 182, 255);
    SDL_RenderDrawLine(ren, cx - 5, DK - 44, cx - 5, DK - 90);
    SDL_RenderDrawLine(ren, cx - 2, DK - 44, cx - 2, DK - 82);
    // top sensor pod
    SDL_SetRenderDrawColor(ren, 148, 154, 162, 255);
    SDL_Rect mast_top = {cx - 10, DK - 96, 14, 8};
    SDL_RenderFillRect(ren, &mast_top);
    // yardarms
    SDL_SetRenderDrawColor(ren, 158, 164, 172, 255);
    SDL_RenderDrawLine(ren, cx - 20, DK - 74, cx + 14, DK - 74);
    SDL_RenderDrawLine(ren, cx - 17, DK - 64, cx + 11, DK - 64);
    // antenna stays
    SDL_SetRenderDrawColor(ren, 128, 134, 142, 255);
    SDL_RenderDrawLine(ren, cx - 20, DK - 74, cx - 5, DK - 90);
    SDL_RenderDrawLine(ren, cx + 14, DK - 74, cx - 2, DK - 82);

    // -- funnel / exhaust uptake --
    SDL_SetRenderDrawColor(ren, 106, 114, 122, 255);
    SDL_Rect funnelb = {cx - 48, FDK, 18, DK - FDK + 20};
    SDL_RenderFillRect(ren, &funnelb);
    SDL_SetRenderDrawColor(ren, 88, 95, 104, 255);
    SDL_Rect funnel_top_rect = {cx - 50, FDK - 6, 22, 7};
    SDL_RenderFillRect(ren, &funnel_top_rect);
    SDL_SetRenderDrawColor(ren, 32, 36, 40, 255);
    SDL_Rect funnel_opening = {cx - 49, FDK - 5, 20, 4};
    SDL_RenderFillRect(ren, &funnel_opening);

    // -- aft superstructure --
    SDL_SetRenderDrawColor(ren, 136, 146, 156, 255);
    SDL_Rect aft_lo = {cx - 78, FDK, 26, DK - FDK};
    SDL_RenderFillRect(ren, &aft_lo);
    SDL_Rect aft_hi = {cx - 76, DK - 26, 22, 26 - (DK - FDK)};
    SDL_RenderFillRect(ren, &aft_hi);
    SDL_Rect aft_top_rect = {cx - 74, DK - 32, 18, 7};
    SDL_RenderFillRect(ren, &aft_top_rect);

    // -- aft mast + sensor --
    SDL_SetRenderDrawColor(ren, 158, 164, 172, 255);
    SDL_RenderDrawLine(ren, cx - 66, DK - 32, cx - 66, DK - 56);
    SDL_RenderDrawLine(ren, cx - 74, DK - 48, cx - 58, DK - 48);
    SDL_RenderDrawLine(ren, cx - 72, DK - 40, cx - 60, DK - 40);

    // -- VLS aft cells (aft of bridge, on main deck) --
    SDL_SetRenderDrawColor(ren, 108, 116, 126, 255);
    SDL_Rect vls_a = {cx - 15, DK - 3, 28, 3};
    SDL_RenderFillRect(ren, &vls_a);
    SDL_SetRenderDrawColor(ren, 82, 89, 99, 255);
    for (int v = 1; v < 4; v++)
        SDL_RenderDrawLine(ren, cx-15+v*7, DK-3, cx-15+v*7, DK);

    // -- helicopter deck (stern, flat, with H marking) --
    SDL_SetRenderDrawColor(ren, 112, 122, 132, 255);
    SDL_Rect helo = {SL + 6, FDK, cx - 79 - SL - 6, DK - FDK};
    SDL_RenderFillRect(ren, &helo);
    // H-marking
    SDL_SetRenderDrawColor(ren, 80, 90, 100, 255);
    int hx = SL + 6 + (cx - 79 - SL - 6) / 2;
    SDL_RenderDrawLine(ren, hx - 7, FDK + 3, hx - 7, FDK + 10);
    SDL_RenderDrawLine(ren, hx + 7, FDK + 3, hx + 7, FDK + 10);
    SDL_RenderDrawLine(ren, hx - 7, FDK + 6, hx + 7, FDK + 6);

    // -- hull outline --
    SDL_SetRenderDrawColor(ren, 65, 75, 84, 255);
    SDL_RenderDrawLine(ren, SL + 4, DK,     BR - 12, DK);      // main deck
    SDL_RenderDrawLine(ren, BR - 12, DK,    BR + 12, cy - 5);  // bow slope
    SDL_RenderDrawLine(ren, BR + 12, cy-5,  BR + 10, BK - 2);  // bow face
    SDL_RenderDrawLine(ren, BR + 10, BK-2,  BR - 12, BK);      // bow keel
    SDL_RenderDrawLine(ren, BR - 12, BK,    SL + 6,  BK);      // keel
    SDL_RenderDrawLine(ren, SL + 4,  DK,    SL + 4,  BK + 1);  // stern

    // -- wake lines astern --
    SDL_SetRenderDrawColor(ren, 28, 72, 120, 200);
    SDL_RenderDrawLine(ren, SL + 4, cy,     SL - 10, cy + 3);
    SDL_RenderDrawLine(ren, SL + 4, cy + 2, SL - 18, cy + 5);
    SDL_RenderDrawLine(ren, SL + 4, cy - 1, SL - 14, cy + 2);
}

// Launch plume: expanding stippled smoke cloud at bow
static void draw_plume(SDL_Renderer* ren, const LaunchPlume& p) {
    float frac = p.age / p.life;
    float r = 4.0f + 18.0f * frac;
    Uint8 bright = Uint8(230.0f * (1.0f - frac));
    SDL_SetRenderDrawColor(ren, bright, bright, bright, 255);
    int ri = int(r);
    for (int dy = -ri; dy <= ri; dy++) {
        for (int dx = -ri; dx <= ri; dx++) {
            if (dx*dx + dy*dy <= ri*ri && ((dx + dy) & 1) == 0)
                SDL_RenderDrawPoint(ren, int(p.x)+dx, int(p.y)+dy);
        }
    }
}

// Draw interceptor missile (small bright triangle + exhaust glow)
static void draw_interceptor(SDL_Renderer* ren, float x, float y, float angle) {
    float ca = cosf(angle), sa = sinf(angle);
    auto pt = [&](float fwd, float rt) -> SDL_Point {
        return { int(x + ca*fwd - sa*rt), int(y + sa*fwd + ca*rt) };
    };
    SDL_SetRenderDrawColor(ren, 200, 255, 200, 255);
    SDL_Point tip = pt(6,0), bl = pt(-3,3), br = pt(-3,-3);
    SDL_RenderDrawLine(ren, tip.x, tip.y, bl.x,  bl.y );
    SDL_RenderDrawLine(ren, tip.x, tip.y, br.x,  br.y );
    SDL_RenderDrawLine(ren, bl.x,  bl.y,  br.x,  br.y );
    SDL_SetRenderDrawColor(ren, 255, 220, 80, 255);
    SDL_Point e1 = pt(-4,0), e2 = pt(-9,0);
    SDL_RenderDrawLine(ren, e1.x, e1.y, e2.x, e2.y);
}

// Kill blast: expanding ring + radial sparks + central flash
static void draw_blast(SDL_Renderer* ren, const KillBlast& b) {
    float frac = b.age / b.life;
    float r = 4.0f + 24.0f * frac;
    // Central flash (white-yellow, fades quickly)
    if (frac < 0.35f) {
        float fr = 8.0f * (1.0f - frac / 0.35f);
        SDL_SetRenderDrawColor(ren, 255, 255, 210, 255);
        SDL_Rect fl = {int(b.x - fr), int(b.y - fr), int(2*fr+1), int(2*fr+1)};
        SDL_RenderFillRect(ren, &fl);
    }
    // Expanding orange ring
    SDL_SetRenderDrawColor(ren, 255, Uint8(160.0f * (1.0f - frac*0.5f)), 0, 255);
    for (int deg = 0; deg < 360; deg += 4) {
        float a = deg * 3.14159f / 180.0f;
        SDL_RenderDrawPoint(ren, int(b.x + r     * cosf(a)), int(b.y + r     * sinf(a)));
        SDL_RenderDrawPoint(ren, int(b.x + (r+1) * cosf(a)), int(b.y + (r+1) * sinf(a)));
    }
    // Radial sparks
    SDL_SetRenderDrawColor(ren, 255, 220, 50, 255);
    for (int s = 0; s < 8; s++) {
        float a = s * 3.14159f / 4.0f;
        SDL_RenderDrawLine(ren,
            int(b.x + r*0.6f * cosf(a)), int(b.y + r*0.6f * sinf(a)),
            int(b.x + (r+5)  * cosf(a)), int(b.y + (r+5)  * sinf(a)));
    }
}

#ifdef USE_CONNEXT
// DDS globals
static ship::ThreatDataWriter *g_threat_writer = nullptr;

class SensorDetectionListener : public DDSDataReaderListener {
public:
    std::map<int, ship::SensorDetection> latest;      // keyed by sensor_id
    std::map<int, std::chrono::steady_clock::time_point> last_seen;
    std::mutex mtx;
    void on_data_available(DDSDataReader* reader) override {
        ship::SensorDetectionDataReader *sr = ship::SensorDetectionDataReader::narrow(reader);
        if (!sr) return;
        ship::SensorDetectionSeq seq;
        DDS_SampleInfoSeq infos;
        DDS_ReturnCode_t ret = sr->take(seq, infos, DDS_LENGTH_UNLIMITED,
                                        DDS_ANY_SAMPLE_STATE, DDS_ANY_VIEW_STATE, DDS_ANY_INSTANCE_STATE);
        if (ret == DDS_RETCODE_OK) {
            std::lock_guard<std::mutex> lk(mtx);
            for (DDS_Long i = 0; i < seq.length(); ++i) {
                latest[seq[i].sensor_id]    = seq[i];
                last_seen[seq[i].sensor_id] = std::chrono::steady_clock::now();
            }
        }
        if (ret == DDS_RETCODE_OK)
            sr->return_loan(seq, infos);
    }
};

// Effect event queued by listener for main thread to consume
struct EffectEvent { float lx, ly; int target_id; int effector_id; bool will_kill; };

class EffectorActionListener : public DDSDataReaderListener {
public:
    std::map<int, ship::EffectorAction> latest;
    std::map<int, std::chrono::steady_clock::time_point> last_seen;
    std::vector<EffectEvent> pending_fx;   // drained each frame by main loop
    std::mutex mtx;
    void on_data_available(DDSDataReader* reader) override {
        ship::EffectorActionDataReader *sr = ship::EffectorActionDataReader::narrow(reader);
        if (!sr) return;
        ship::EffectorActionSeq seq;
        DDS_SampleInfoSeq infos;
        DDS_ReturnCode_t ret = sr->take(seq, infos, DDS_LENGTH_UNLIMITED,
                                        DDS_ANY_SAMPLE_STATE, DDS_ANY_VIEW_STATE, DDS_ANY_INSTANCE_STATE);
        if (ret == DDS_RETCODE_OK) {
            std::lock_guard<std::mutex> lk(mtx);
            for (DDS_Long i = 0; i < seq.length(); ++i) {
                latest[seq[i].effector_id]    = seq[i];
                last_seen[seq[i].effector_id] = std::chrono::steady_clock::now();
                // Queue visual effect: plume at bow, optional blast at threat
                pending_fx.push_back({
                    float(SHIP_X + 40), float(SHIP_Y - 26),   // VLS on forward deck
                    int(seq[i].threat_id),
                    int(seq[i].effector_id),
                    seq[i].destroyed != DDS_BOOLEAN_FALSE
                });
            }
        }
        if (ret == DDS_RETCODE_OK)
            sr->return_loan(seq, infos);
    }
};

#endif

#ifdef USE_CONNEXT
static SensorDetectionListener sensor_listener;
static EffectorActionListener effector_listener;
#endif

void publishThreat(const ship::Threat &t)
{
#ifdef USE_CONNEXT
    if (g_threat_writer) {
        ship::Threat sample = t;
        DDS_ReturnCode_t ret = g_threat_writer->write(sample, DDS_HANDLE_NIL);
        if (ret != DDS_RETCODE_OK) std::cerr << "Threat write failed: " << ret << std::endl;
        return;
    }
#endif
    std::cout << "[PUB] Threat id=" << t.id << " x=" << t.x << " y=" << t.y << "\n";
}

int main(int argc, char **argv)
{
    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        std::cerr << "SDL_Init Error: " << SDL_GetError() << std::endl;
        return 1;
    }

    SDL_Window *win = SDL_CreateWindow("Ship Defense - Command & Control", 100, 100, 1060, 600, SDL_WINDOW_SHOWN);
    if (!win) {
        std::cerr << "SDL_CreateWindow Error: " << SDL_GetError() << std::endl;
        SDL_Quit();
        return 1;
    }

    SDL_Renderer *ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!ren) {
        SDL_DestroyWindow(win);
        std::cerr << "SDL_CreateRenderer Error: " << SDL_GetError() << std::endl;
        SDL_Quit();
        return 1;
    }

    // Load ship photo texture — resolve path relative to the executable directory
    // so it works regardless of the working directory the user launches from.
    IMG_Init(IMG_INIT_PNG);
    SDL_Texture* ship_tex = nullptr;
    {
        char img_path[2048] = {};
        char* base = SDL_GetBasePath();   // e.g. "C:\...\Debug\"
        if (base) {
            SDL_snprintf(img_path, sizeof(img_path), "%sArleighBurke-class.png", base);
            SDL_free(base);
        } else {
            SDL_strlcpy(img_path, "ArleighBurke-class.png", sizeof(img_path));
        }
        SDL_Surface* surf = IMG_Load(img_path);
        if (surf) {
            ship_tex = SDL_CreateTextureFromSurface(ren, surf);
            SDL_SetTextureBlendMode(ship_tex, SDL_BLENDMODE_BLEND);  // honour PNG alpha
            SDL_FreeSurface(surf);
        } else {
            std::cerr << "IMG_Load (" << img_path << "): " << IMG_GetError() << std::endl;
        }
    }

    bool running = true;
    SDL_Event e;
    std::vector<ship::Threat> threats;
    std::vector<LaunchPlume>  plumes;
    std::vector<KillBlast>    blasts;
    std::vector<Interceptor>  interceptors;
    int next_id = 1;
    std::mutex data_mtx;

#ifdef USE_CONNEXT
    // DDS setup
    DDSDomainParticipant *participant = DDSDomainParticipantFactory::get_instance()->create_participant(
        0, DDS_PARTICIPANT_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
    if (participant == NULL) {
        std::cerr << "create_participant error" << std::endl;
    } else {
        // register types
        ship::ThreatTypeSupport::register_type(participant, ship::ThreatTypeSupport::get_type_name());
        ship::SensorDetectionTypeSupport::register_type(participant, ship::SensorDetectionTypeSupport::get_type_name());
        ship::EffectorActionTypeSupport::register_type(participant, ship::EffectorActionTypeSupport::get_type_name());

        // create topics
        DDSTopic *threat_topic = participant->create_topic("ThreatTopic",
            ship::ThreatTypeSupport::get_type_name(), DDS_TOPIC_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
        DDSTopic *sensor_topic = participant->create_topic("SensorDetectionTopic",
            ship::SensorDetectionTypeSupport::get_type_name(), DDS_TOPIC_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
        DDSTopic *effector_topic = participant->create_topic("EffectorActionTopic",
            ship::EffectorActionTypeSupport::get_type_name(), DDS_TOPIC_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);

        // publisher/writer
        DDSPublisher *publisher = participant->create_publisher(DDS_PUBLISHER_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
        DDSDataWriter *dw = publisher->create_datawriter(threat_topic, DDS_DATAWRITER_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
        g_threat_writer = ship::ThreatDataWriter::narrow(dw);

        // subscriber/listeners
        DDSSubscriber *subscriber = participant->create_subscriber(DDS_SUBSCRIBER_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);

        DDSDataReader *sd_dr = subscriber->create_datareader(sensor_topic, DDS_DATAREADER_QOS_DEFAULT, &sensor_listener, DDS_DATA_AVAILABLE_STATUS);

        DDSDataReader *ea_dr = subscriber->create_datareader(effector_topic, DDS_DATAREADER_QOS_DEFAULT, &effector_listener, DDS_DATA_AVAILABLE_STATUS);
    }
#endif

    auto last          = std::chrono::steady_clock::now();
    auto last_republish = std::chrono::steady_clock::now();

    while (running) {
        while (SDL_PollEvent(&e)) {
            if (e.type == SDL_QUIT) running = false;
            if (e.type == SDL_MOUSEBUTTONDOWN && e.button.x < 800 && e.button.y < 560) {
                int x = e.button.x;
                int y = e.button.y;
                ship::Threat t;
                t.id = next_id++;
                t.x = x;
                t.y = y;
                t.heading = 180.0;
                t.speed = 22.0;   // px/sec — slow enough to track visually
                t.severity = 1;
                threats.push_back(t);
                publishThreat(t);
            }
        }

        auto now = std::chrono::steady_clock::now();
        std::chrono::duration<double> dt = now - last;
        last = now;

        // Update threats (move toward ship bow)
        const int cx = SHIP_X, cy = SHIP_Y;
        for (auto &t : threats) {
            double dx = cx - t.x;
            double dy = (cy - 16) - t.y;   // aim at main deck (side view)
            double dist = std::sqrt(dx*dx + dy*dy);
            if (dist > 1e-6) {
                t.x += (dx / dist) * t.speed * dt.count();
                t.y += (dy / dist) * t.speed * dt.count();
            }
        }

        // Republish current threat positions every 500 ms so sensor range-checks work
        {
            auto rep_now = std::chrono::steady_clock::now();
            if (rep_now - last_republish >= std::chrono::milliseconds(500)) {
                last_republish = rep_now;
                for (auto& t : threats) publishThreat(t);
            }
        }

        // Cull threats that reach the hull (50 px from ship center)
        threats.erase(std::remove_if(threats.begin(), threats.end(), [&](const ship::Threat &t){
            double dx = cx - t.x; double dy = cy - t.y; return (dx*dx+dy*dy) < 4900.0; }), threats.end());

    // Drain new effect events from effector listener
#ifdef USE_CONNEXT
        {
            std::lock_guard<std::mutex> lk(effector_listener.mtx);
            for (auto& ev : effector_listener.pending_fx) {
                plumes.push_back({ev.lx, ev.ly, 0.0f, 1.4f});
                // Speed varies by weapon type
                float spd = 150.0f;
                switch (ev.effector_id) {
                    case 1: spd = 150.0f; break;  // SM-2 MR
                    case 2: spd = 175.0f; break;  // SM-6
                    case 3: spd = 130.0f; break;  // ESSM
                    case 4: spd = 210.0f; break;  // CIWS
                    case 5: spd = 100.0f; break;  // MK45
                }
                interceptors.push_back({ev.lx, ev.ly, ev.target_id, spd, 0.0f, 20.0f, ev.will_kill, false});
            }
            effector_listener.pending_fx.clear();
        }
#else
        {
            // Local fallback (no DDS): emulate sensor detections and layered weapon engagements.
            static std::mt19937 rng{(unsigned)std::chrono::system_clock::now().time_since_epoch().count()};
            static std::uniform_int_distribution<int> conf_dist_spy(88, 100);
            static std::uniform_int_distribution<int> conf_dist_spq(72, 90);
            static std::uniform_int_distribution<int> conf_dist_sps(55, 75);
            static std::uniform_int_distribution<int> conf_dist_slq(65, 85);
            static std::uniform_int_distribution<int> chance(1, 100);
            static std::set<int> engaged_ids;

            const auto now2 = std::chrono::steady_clock::now();

            for (const auto& t : threats) {
                const float dx = float(t.x) - float(SHIP_X);
                const float dy = float(t.y) - float(SHIP_Y);
                const float dist = sqrtf(dx*dx + dy*dy);

                // Sensor rings (same radii used in sensor app comments)
                struct SensorCfg { int id; float range_px; std::uniform_int_distribution<int>* conf; };
                SensorCfg sensors[] = {
                    {1, 412.0f, &conf_dist_spy}, // AN/SPY-1D
                    {2,  75.0f, &conf_dist_spq}, // AN/SPQ-9B
                    {3,  47.0f, &conf_dist_sps}, // AN/SPS-67
                    {4, 187.0f, &conf_dist_slq}, // AN/SLQ-32
                };
                for (const auto& s : sensors) {
                    if (dist <= s.range_px) {
                        ship::SensorDetection d;
                        d.sensor_id = s.id;
                        d.threat_id = t.id;
                        d.x = t.x;
                        d.y = t.y;
                        d.confidence = (*(s.conf))(rng);
                        (void)d; // retained for parity with DDS path; currently visuals are interceptor-driven
                    }
                }

                // Engage once when threat crosses in-range boundary.
                if (dist <= 380.0f && engaged_ids.insert(t.id).second) {
                    struct EffectorCfg { int id; int pk; float speed; bool surface_only; };
                    EffectorCfg effectors[] = {
                        {1, 75, 150.0f, false}, // SM-2 MR
                        {2, 87, 175.0f, false}, // SM-6
                        {3, 68, 130.0f, false}, // ESSM
                        {4, 52, 210.0f, false}, // CIWS
                        {5, 36, 100.0f, true }, // MK45/62
                    };

                    for (const auto& efx : effectors) {
                        if (efx.surface_only && t.severity < 3) continue;
                        const bool will_kill = (chance(rng) <= efx.pk);
                        plumes.push_back({float(SHIP_X + 40), float(SHIP_Y - 26), 0.0f, 1.4f});
                        interceptors.push_back({
                            float(SHIP_X + 40),
                            float(SHIP_Y - 26),
                            t.id,
                            efx.speed,
                            0.0f,
                            20.0f,
                            will_kill,
                            false
                        });
                    }
                }
            }
        }
#endif
        // Age and expire effects
        float dtf = float(dt.count());
        for (auto& p : plumes) p.age += dtf;
        for (auto& b : blasts) b.age += dtf;
        plumes.erase(std::remove_if(plumes.begin(), plumes.end(),
            [](const LaunchPlume& p){ return p.age >= p.life; }), plumes.end());
        blasts.erase(std::remove_if(blasts.begin(), blasts.end(),
            [](const KillBlast& b){ return b.age >= b.life; }), blasts.end());

        // Update interceptors: track moving targets, trigger blast on contact
        std::vector<int> kill_ids;
        for (auto& ic : interceptors) {
            if (ic.done) continue;
            ic.age += dtf;
            const ship::Threat* tgt = nullptr;
            for (const auto& th : threats) { if (th.id == ic.target_id) { tgt = &th; break; } }
            if (!tgt) { ic.done = true; continue; }   // target already gone
            float dx = float(tgt->x) - ic.x, dy = float(tgt->y) - ic.y;
            float dist = sqrtf(dx*dx + dy*dy);
            if (dist < 10.0f) {
                ic.done = true;
                float blife = ic.will_kill ? 1.4f : 0.7f;   // bigger blast for kills
                blasts.push_back({ic.x, ic.y, 0.0f, blife});
                if (ic.will_kill) {
                    bool dup = false;
                    for (int k : kill_ids) if (k == ic.target_id) { dup = true; break; }
                    if (!dup) kill_ids.push_back(ic.target_id);
                }
            } else {
                ic.x += (dx / dist) * ic.speed * dtf;
                ic.y += (dy / dist) * ic.speed * dtf;
            }
        }
        interceptors.erase(std::remove_if(interceptors.begin(), interceptors.end(),
            [](const Interceptor& ic){ return ic.done || ic.age >= ic.life; }), interceptors.end());
        for (int kid : kill_ids)
            threats.erase(std::remove_if(threats.begin(), threats.end(),
                [kid](const ship::Threat& th){ return th.id == kid; }), threats.end());


        // Render
        SDL_SetRenderDrawColor(ren, 10, 20, 40, 255);   // ocean at night
        SDL_RenderClear(ren);

        // Subtle ocean surface texture
        SDL_SetRenderDrawColor(ren, 15, 30, 55, 255);
        for (int wy = 60; wy < 600; wy += 18)
            SDL_RenderDrawLine(ren, 0, wy, 799, wy);

        // Deep water below the waterline
        SDL_Rect deepsea = {0, SHIP_Y - 2, 800, 600 - (SHIP_Y - 2)};
        SDL_SetRenderDrawColor(ren, 8, 16, 32, 255);
        SDL_RenderFillRect(ren, &deepsea);

        // Radar range rings centred on ship (green, every 100 px)
        SDL_SetRenderDrawColor(ren, 20, 55, 30, 255);
        for (int ring = 100; ring <= 450; ring += 100) {
            for (int deg = 0; deg < 360; deg += 3) {
                float ang = deg * 3.14159f / 180.0f;
                SDL_RenderDrawPoint(ren, cx + int(ring * cosf(ang)), cy + int(ring * sinf(ang)));
            }
        }

        // SPY-1D detection range ring — dashed light red arc (412 px = 220 nm)
        SDL_SetRenderDrawColor(ren, 180, 45, 45, 255);
        for (int deg = 0; deg < 360; deg++) {
            if (deg % 6 >= 3) continue;   // 3-on / 3-off dash pattern
            float ang = deg * 3.14159f / 180.0f;
            int rx = cx + int(412 * cosf(ang));
            int ry = cy + int(412 * sinf(ang));
            if (rx >= 0 && rx < 800 && ry >= 0 && ry < 600)
                SDL_RenderDrawPoint(ren, rx, ry);
        }

        // Launch plumes (behind ship so hull draws on top)
        for (auto& p : plumes) draw_plume(ren, p);

        // Ship photo (or drawn fallback)
        if (ship_tex) {
            int tw, th;
            SDL_QueryTexture(ship_tex, nullptr, nullptr, &tw, &th);
            // Size by height: ~1/2 inch tall at 96 DPI
            const int DISP_H = 48;
            int disp_w = (th > 0) ? DISP_H * tw / th : 160;
            SDL_Rect dst = {cx - disp_w / 2, cy + 5 - DISP_H, disp_w, DISP_H};
            SDL_RenderCopy(ren, ship_tex, nullptr, &dst);
        } else {
            draw_destroyer(ren, cx, cy);
        }

        // Threats (typed shapes oriented toward the ship)
        for (auto& t : threats) {
            float tdx = float(cx)      - float(t.x);
            float tdy = float(cy - 16) - float(t.y);
            draw_threat(ren, int(t.x), int(t.y), atan2f(tdy, tdx), t.id % 3);

            // Extra visibility: yellow blip ring + small T# label
            SDL_SetRenderDrawColor(ren, 245, 220, 70, 255);
            SDL_Rect blip = {int(t.x) - 6, int(t.y) - 6, 12, 12};
            SDL_RenderDrawRect(ren, &blip);
            char tbuf[16];
            std::snprintf(tbuf, sizeof(tbuf), "T#%d", t.id);
            draw_text(ren, int(t.x) + 8, int(t.y) - 8, tbuf, 1);
        }

        // Operator hint + live threat count
        SDL_SetRenderDrawColor(ren, 180, 190, 210, 255);
        draw_text(ren, 10, 8, "Click in map (left side) to spawn inbound threats", 1);
        char th_count[32];
        std::snprintf(th_count, sizeof(th_count), "Active threats: %zu", threats.size());
        draw_text(ren, 10, 20, th_count, 1);

        // Interceptor missiles (above threats, below blasts)
        for (const auto& ic : interceptors) {
            if (ic.done) continue;
            float angle = -1.5708f;   // default: pointing up
            for (const auto& th : threats) {
                if (th.id == ic.target_id) {
                    angle = atan2f(float(th.y) - ic.y, float(th.x) - ic.x);
                    break;
                }
            }
            draw_interceptor(ren, ic.x, ic.y, angle);
        }

        // Kill/intercept blasts (topmost layer)
        for (auto& b : blasts) draw_blast(ren, b);

#ifdef USE_CONNEXT
        // Dotted radar-track lines from each detection point to ship bow
        {
            std::lock_guard<std::mutex> lk(sensor_listener.mtx);
            SDL_SetRenderDrawColor(ren, 150, 145, 25, 255);
            for (auto &[sid, d] : sensor_listener.latest) {
                int x1 = int(d.x), y1 = int(d.y), x2 = cx, y2 = cy - 16;
                float len = sqrtf(float((x2-x1)*(x2-x1)+(y2-y1)*(y2-y1)));
                int steps = int(len);
                for (int s = 0; s < steps; s += 8) {
                    float fr = float(s) / float(steps > 0 ? steps : 1);
                    SDL_RenderDrawPoint(ren, x1 + int((x2-x1)*fr), y1 + int((y2-y1)*fr));
                }
            }
        }
        // (effector visuals are handled by the plume / blast effect system above)

        // ---- Status Panel (right 250 px) ----
        {
            const int PX         = 810;   // panel left edge
            const int PW         = 246;   // panel width
            const int COL_NAME   = 813;   // system name  (9 chars = 54 px)
            const int COL_THREAT = 877;   // threat / target column
            const int COL_CONF   = 925;   // conf / status column
            const int COL_TARGET = COL_THREAT;
            const int COL_STATUS = COL_CONF;

            // Panel background + left border
            SDL_Rect pbg = {PX, 0, PW, 600};
            SDL_SetRenderDrawColor(ren, 22, 22, 32, 255);
            SDL_RenderFillRect(ren, &pbg);
            SDL_SetRenderDrawColor(ren, 65, 65, 85, 255);
            SDL_RenderDrawLine(ren, PX, 0, PX, 599);

            int pcy = 8;
            auto panel_sep = [&]() {
                SDL_SetRenderDrawColor(ren, 65, 65, 85, 255);
                SDL_RenderDrawLine(ren, PX + 2, pcy, PX + PW - 4, pcy);
                pcy += 5;
            };

            // ---- SENSORS ----
            SDL_SetRenderDrawColor(ren, 240, 210, 60, 255);
            draw_text(ren, COL_NAME, pcy, "SENSORS", 2);
            pcy += 20;
            panel_sep();
            SDL_SetRenderDrawColor(ren, 100, 100, 120, 255);
            draw_text(ren, COL_NAME,   pcy, "SENSOR", 1);
            draw_text(ren, COL_THREAT, pcy, "THREAT", 1);
            draw_text(ren, COL_CONF,   pcy, "CONF",   1);
            pcy += 11;
            panel_sep();
            {
                std::lock_guard<std::mutex> lk2(sensor_listener.mtx);
                auto now2 = std::chrono::steady_clock::now();
                for (auto &[sid, d] : sensor_listener.latest) {
                    bool active = sensor_listener.last_seen.count(sid) > 0 &&
                                  (now2 - sensor_listener.last_seen.at(sid)) < std::chrono::seconds(5);
                    char buf[24];
                    if (active) SDL_SetRenderDrawColor(ren,  80, 220,  80, 255);
                    else        SDL_SetRenderDrawColor(ren, 110, 110, 110, 255);
                    draw_text(ren, COL_NAME, pcy, sensor_name(sid), 1);
                    if (active) {
                        snprintf(buf, sizeof(buf), "T#%-5d", d.threat_id);
                        draw_text(ren, COL_THREAT, pcy, buf, 1);
                        snprintf(buf, sizeof(buf), "%3d%%", d.confidence);
                        draw_text(ren, COL_CONF, pcy, buf, 1);
                    } else {
                        draw_text(ren, COL_THREAT, pcy, "IDLE   ", 1);
                        draw_text(ren, COL_CONF,   pcy, " --",     1);
                    }
                    pcy += 11;
                }
                if (sensor_listener.latest.empty()) {
                    SDL_SetRenderDrawColor(ren, 80, 80, 80, 255);
                    draw_text(ren, COL_NAME, pcy, "none", 1);
                    pcy += 11;
                }
            }

            // ---- EFFECTORS ----
            pcy += 4;
            panel_sep();
            SDL_SetRenderDrawColor(ren, 60, 200, 240, 255);
            draw_text(ren, COL_NAME, pcy, "EFFECTORS", 2);
            pcy += 20;
            panel_sep();
            SDL_SetRenderDrawColor(ren, 100, 100, 120, 255);
            draw_text(ren, COL_NAME,   pcy, "WEAPON", 1);
            draw_text(ren, COL_TARGET, pcy, "TARGET", 1);
            draw_text(ren, COL_STATUS, pcy, "STATUS", 1);
            pcy += 11;
            panel_sep();
            {
                std::lock_guard<std::mutex> lk2(effector_listener.mtx);
                auto now2 = std::chrono::steady_clock::now();
                for (auto &[eid, a] : effector_listener.latest) {
                    bool active = effector_listener.last_seen.count(eid) > 0 &&
                                  (now2 - effector_listener.last_seen.at(eid)) < std::chrono::seconds(5);
                    char buf[24];
                    if      (!active)     SDL_SetRenderDrawColor(ren, 110, 110, 110, 255);
                    else if (a.destroyed) SDL_SetRenderDrawColor(ren, 255, 160,   0, 255);
                    else                  SDL_SetRenderDrawColor(ren,  80, 220,  80, 255);
                    draw_text(ren, COL_NAME, pcy, effector_name(eid), 1);
                    if (active) {
                        snprintf(buf, sizeof(buf), "T#%-5d", a.threat_id);
                        draw_text(ren, COL_TARGET, pcy, buf, 1);
                        draw_text(ren, COL_STATUS, pcy, a.destroyed ? "KILL  " : "FIRING", 1);
                    } else {
                        draw_text(ren, COL_TARGET, pcy, " --   ", 1);
                        draw_text(ren, COL_STATUS, pcy, "IDLE  ", 1);
                    }
                    pcy += 11;
                }
                if (effector_listener.latest.empty()) {
                    SDL_SetRenderDrawColor(ren, 80, 80, 80, 255);
                    draw_text(ren, COL_NAME, pcy, "none", 1);
                }
            }

            // ---- INCOMING THREATS ----
            pcy += 4;
            panel_sep();
            SDL_SetRenderDrawColor(ren, 230, 80, 80, 255);
            draw_text(ren, COL_NAME, pcy, "THREATS", 2);
            pcy += 20;
            panel_sep();
            SDL_SetRenderDrawColor(ren, 100, 100, 120, 255);
            draw_text(ren, 813, pcy, "ID",   1);
            draw_text(ren, 845, pcy, "TYPE", 1);
            draw_text(ren, 893, pcy, "SPD",  1);
            draw_text(ren, 933, pcy, "TTI",  1);
            pcy += 11;
            panel_sep();
            if (threats.empty()) {
                SDL_SetRenderDrawColor(ren, 80, 80, 80, 255);
                draw_text(ren, 813, pcy, "NO CONTACTS", 1);
                pcy += 11;
            } else {
                for (auto& t : threats) {
                    if (pcy + 11 > 592) break;   // guard panel overflow
                    float dx_t = float(t.x) - 400.0f;
                    float dy_t = float(t.y) - 570.0f;
                    float dist_t = sqrtf(dx_t*dx_t + dy_t*dy_t);
                    float tti   = (t.speed > 0.01) ? dist_t / float(t.speed) : 99.0f;
                    int   spd_kt = int(t.speed * 30);  // scale to notional knots for display
                    const char* type_str =
                        (t.id % 3 == 0) ? "BALST" :
                        (t.id % 3 == 1) ? "DRONE" : "ASCM ";
                    char buf[32];
                    SDL_SetRenderDrawColor(ren, 220, 90, 90, 255);
                    snprintf(buf, sizeof(buf), "T#%d", t.id);
                    draw_text(ren, 813, pcy, buf, 1);
                    draw_text(ren, 845, pcy, type_str, 1);
                    snprintf(buf, sizeof(buf), "%dkt", spd_kt);
                    draw_text(ren, 893, pcy, buf, 1);
                    snprintf(buf, sizeof(buf), "%3.0fs", tti);
                    draw_text(ren, 933, pcy, buf, 1);
                    pcy += 11;
                }
            }
        }
        // ---- End Status Panel ----
#endif

        SDL_RenderPresent(ren);

        std::this_thread::sleep_for(10ms);
    }

    if (ship_tex) SDL_DestroyTexture(ship_tex);
    IMG_Quit();
    SDL_DestroyRenderer(ren);
    SDL_DestroyWindow(win);
    SDL_Quit();
    return 0;
}
