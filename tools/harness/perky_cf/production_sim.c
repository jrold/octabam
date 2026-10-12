/* End-to-end production simulation for the PERKY 3ALGO machine.
 *
 * Calls the REAL entry points, in the order the unit does:
 *
 *   pk_engine_select(model)   the panel/browser mapping -- the SAME function the
 *                             engine list calls when a row is picked, so the
 *                             model byte reaches the page slot the way a user
 *                             selection puts it there
 *   pk_render(track, ...)     the REAL control path, which prepares the controls
 *                             and writes the DSP record INCLUDING the resonant
 *                             fresh state this branch added
 *
 * and then dumps the whole DSP record buffer as 16-bit words. Nothing here seeds
 * voice state, forces n7, or calls a renderer: this is the producer side only.
 *
 * Input rows, 3 bytes each: track, trig, model.
 * Output: (WORDS * 2) bytes per row, little-endian u16 DSP words, word 0 first.
 *
 * `pk_engine_select` calls two absolute addresses in the stock OS; both are
 * mapped here and patched to a bare `ret`, because this harness is the PRODUCER
 * and has no UI to redraw. Every other call it makes is real.
 */
#include <sys/mman.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>

#define U8(a)  (*(volatile uint8_t  *)(uintptr_t)(a))
#define U16(a) (*(volatile uint16_t *)(uintptr_t)(a))
#define U32(a) (*(volatile uint32_t *)(uintptr_t)(a))

extern int  pk_render(unsigned, unsigned, unsigned, unsigned);
extern void pk_engine_select(unsigned model);
extern void pk_engine_open(void);
void pk_stock_pool_open(void) { abort(); }
int  pk_stock_validate(void *p) { abort(); }

#define WORDS 128u          /* covers the record and the fresh-state words */

static void map_at(uintptr_t at, unsigned size, int prot)
{
    void *p = mmap((void *)at, size, prot,
                   MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0);
    if (p != (void *)at) { perror("mmap"); exit(2); }
}

int main(int argc, char **argv)
{
    map_at(0x10000000u, 0x200000u, PROT_READ | PROT_WRITE);
    /* The stock UI entry points are patched to a bare `ret`, so this one page
     * range must be EXECUTABLE as well as writable. */
    map_at(0x40000000u, 0x1000000u, PROT_READ | PROT_WRITE | PROT_EXEC);
    map_at(0x46000000u, 0x4000000u, PROT_READ | PROT_WRITE);
    map_at(0x80000000u, 0x1000000u, PROT_READ | PROT_WRITE);

    /* The stock UI calls the panel path makes. This harness is the PRODUCER --
     * it drives the same functions the UI drives and has no screen -- so each
     * becomes a stub. Everything that DECIDES anything is real.
     *
     * 0x4005829c OPENS THE LIST WINDOW. It must return 0: pk_engine_open stores
     * that in 0x460e5e30 and then `if (!window) return`, so a zero return is the
     * clean "no screen" exit that leaves the bank/part/track it has already
     * captured. A bare `ret` leaves garbage in rax, the draws run, and the
     * harness faults writing a window that does not exist. */
    U8(0x4005829cu) = 0x31;   /* xor eax,eax */
    U8(0x4005829du) = 0xC0;
    U8(0x4005829eu) = 0xC3;   /* ret         */
    U8(0x40027e00u) = 0xC3;   /* pk_engine_select's UI refresh      */
    U8(0x4004d948u) = 0xC3;   /* pk_engine_select's second call     */
    U8(0x4007ec60u) = 0xC3;   /* pk_engine_open's list setup        */
    U8(0x4007edb0u) = 0xC3;   /* pk_engine_open's list selection    */

    U32(0x46c82456u) = 0x48000000u;
    U8(0x100b14cfu) = 0;
    U32(0x800062a8u) = 0x80008000u;
    for (unsigned t = 0; t < 8; t++) {
        uintptr_t p = 0x48000000u + 0x8ed80u;
        U8(p + 0x22u + t) = 1;
        U8(p + 60u + 30u * t) = 'P';
        U8(p + 61u + 30u * t) = 'K';
        U8(p + 62u + 30u * t) = 1;
    }

    FILE *f = fopen(argv[1], "rb");
    FILE *g = fopen(argv[2], "wb");
    if (!f || !g) { perror("open"); return 2; }

    uint8_t row[3];
    unsigned n = 0;
    while (fread(row, 1, 3, f) == 3) {
        const unsigned track = row[0], trig = row[1], model = row[2];
        const unsigned ping = n++ & 1u;

        /* THE PANEL, in the order the unit does it. The engine list is opened
         * for this track -- which is what captures the bank/part/track the
         * selector's own guard then checks -- and the row is picked. The row
         * handlers in control.c are `static`, and each is exactly one call to
         * pk_engine_select with its own model, so driving that call with the
         * model the handler names IS the panel mapping; the gate reads those
         * models out of control.c rather than assuming them. */
        U8(0x100b14ccu) = (uint8_t)track;
        U32(0x460e5e30u) = 0u;              /* the list is closed */
        pk_engine_open();
        U32(0x460e5e30u) = 0u;              /* ... and re-closed for the pick */
        pk_engine_select(model);

        U8(0x46104d0cu + track) = trig ? 16u : 0u;
        U32(0x80001c80u) = 0x80010000u;
        assert(pk_render(track, ping, 0, 16) == 0);

        const volatile uint32_t *rec = (const volatile uint32_t *)(uintptr_t)
            (0x80001c90u + ping * 0xa80u + 336u * track);
        assert(rec[0] == 0x504b0000u);
        assert(rec[1] == (0x59310000u | trig));

        /* emit the whole record as DSP words: word 0 first, low half then high */
        for (unsigned w = 0; w < WORDS; w++) {
            const uint32_t l = rec[w / 2u];
            const uint16_t v = (uint16_t)((w & 1u) ? l : (l >> 16));
            fputc(v & 255, g);
            fputc((v >> 8) & 255, g);
        }
    }
    fclose(f);
    fclose(g);
    return 0;
}
