#!/usr/bin/env python3
"""Bind the standalone exact stock-mixer proof to a packaged booted image."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/verify'))
import verify_perky_hybrid_runtime as rt


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def symbol_bytes(path,name):
    """Read one sized ELF32 big-endian symbol without changing the ELF."""
    data=Path(path).read_bytes()
    assert data[:6]==b'\x7fELF\x01\x02','expected ELF32 big-endian target'
    header=struct.unpack_from('>16sHHIIIIIHHHHHH',data)
    sections=[struct.unpack_from('>10I',data,header[6]+i*header[11]) for i in range(header[12])]
    for section in sections:
        if section[1]!=2:
            continue
        strings=sections[section[6]]
        names=data[strings[4]:strings[4]+strings[5]]
        for offset in range(section[4],section[4]+section[5],section[9]):
            index,address,size,info,other,section_index=struct.unpack_from('>IIIBBH',data,offset)
            label=names[index:names.index(0,index)].decode()
            if label==name:
                target=sections[section_index]
                start=target[4]+address-target[3]
                assert size>0 and 0<=address-target[3]<=target[5]-size,'symbol range'
                return address,data[start:start+size]
    raise AssertionError(('missing ELF symbol',str(path),name))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--proof',type=Path,default=ROOT/'out/perky/hybrid/stock-source-block-v2/RESULT.json')
    parser.add_argument('--work',type=Path)
    args=parser.parse_args();build=args.build.resolve();proof_path=args.proof.resolve()
    work=(args.work or build/'stock-mixer-binding-v2').resolve();work.mkdir(parents=True,exist_ok=True)
    source=ROOT/'tools/perky/generate_stock_source_mix_block.py'
    spec=importlib.util.spec_from_file_location('stock_mix_binding_generator',source)
    generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
    generator.expected_span()
    proof=json.loads(proof_path.read_text())
    assert proof['status']=='PASS_ACTUAL_COMPLETE_STOCK_MIX_BLOCK_REGS_CCR_EMAC_ALL_MEMORY'
    assert proof['cases']==4096 and proof['same_image_cycle_controls']
    # Every input of the independent proof must still be the exact proven input.
    for path,expected in proof['source_sha256'].items():
        assert sha(path)==expected,('standalone proof input drift',path)
    standalone=proof_path.parent/'kernel.elf'
    assert proof['source_sha256'][str(source)]==sha(source)
    assert proof['source_sha256'][str(standalone)]==sha(standalone)
    metadata=json.loads((build/'BUILD.json').read_text())
    image=build/'probe'/f'mainos_{metadata["version"]}.bin'
    elf=build/'probe/platform/runtime.elf'
    assert sha(image)==metadata['main_sha256'],'final MAIN drift'
    assert sha(elf)==metadata['runtime_sha256'],'final ELF drift'
    name='pk_stock_source_mix_block'
    standalone_address,proven=symbol_bytes(standalone,name)
    actual_address,actual=symbol_bytes(elf,name)
    assert actual==proven,'final linked helper differs from independently executed helper'
    assert actual[-6:]==b'\x4e\xf9'+generator.SITE['continuation'].to_bytes(4,'big'),'fixed original continuation'
    # The earlier proof hashed ELF, while its runner loads kernel.bin and
    # kernel.nm. Reconstruct both from that pinned ELF, require exact equality
    # to the original artifacts, and replay the pinned runner in a NEW private
    # directory. Frozen receipts and proof inputs are never overwritten.
    replay=work/'standalone-replay'
    replay.mkdir(exist_ok=True)
    reconstructed=replay/'elf-objcopy.bin'
    subprocess.run(['m68k-elf-objcopy','-O','binary',str(standalone),str(reconstructed)],check=True)
    original_binary=proof_path.parent/'kernel.bin'
    assert reconstructed.read_bytes()==original_binary.read_bytes(),'executed binary differs from pinned ELF image'
    reconstructed_nm=subprocess.check_output(['m68k-elf-nm','-n',str(standalone)])
    assert reconstructed_nm==(proof_path.parent/'kernel.nm').read_bytes(),'runner symbol addresses differ from pinned ELF'
    shutil.copy2(original_binary,replay/'kernel.bin')
    (replay/'kernel.nm').write_bytes(reconstructed_nm)
    shutil.copy2(proof_path.parent/'runner',replay/'runner')
    assert sha(replay/'runner')==proof['source_sha256'][str(proof_path.parent/'runner')]
    # The standalone linker command fixes the binary load address; this also
    # verifies the exact helper byte slice actually consumed by Target.
    binary_base=0x45000000
    executed_helper=(replay/'kernel.bin').read_bytes()[standalone_address-binary_base:standalone_address-binary_base+len(proven)]
    assert executed_helper==proven,'runner-loaded helper bytes differ from pinned ELF symbol'
    replay_inputs={str(path):sha(path) for path in (replay/'kernel.bin',replay/'kernel.nm',replay/'runner')}
    original_image=Path(proof['commands'][-1][-1])
    assert sha(original_image)==proof['source_sha256'][str(original_image)]
    command=[str(replay/'runner'),str(replay),str(original_image)]
    with (replay/'run.log').open('w') as log:
        subprocess.run(command,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
    for path,expected in replay_inputs.items():
        assert sha(path)==expected,('replay input changed during execution',path)
    execution_path=replay/'EXECUTION.json'
    execution=json.loads(execution_path.read_text())
    assert execution['status']==proof['status'] and execution['cases']==4096
    assert execution['same_image_cycle_controls']
    assert execution['mean_saved_cycles']==proof['mean_saved_cycles']
    detour=b'\x4e\xf9'+actual_address.to_bytes(4,'big')+b'\x4e\x71'
    site=generator.SITE['address'];end=generator.SITE['end'];continuation=generator.SITE['continuation']
    main=image.read_bytes();stock=(ROOT/'out/raw/section_3_MAIN_OS.bin').read_bytes()
    assert main[site-generator.BASE:end-generator.BASE]==detour,'packaged MAIN detour/padding mismatch'
    assert main[end-generator.BASE:continuation-generator.BASE]==stock[end-generator.BASE:continuation-generator.BASE], 'stock remainder changed'
    # Boot the packaged MAIN's real loader. Do not map, patch or inject helper
    # bytes; all checks below are reads of the boot result.
    boot=rt.g.emu.boot(str(image),count=200000000)
    assert boot.clean,(boot.stopped,boot.error)
    symbols=rt.g.load_elf_symbols(elf)
    assert int.from_bytes(boot.uc.mem_read(symbols['pk_hybrid_pcm_cookie'],4),'big')==0x504b5052
    assert int.from_bytes(boot.uc.mem_read(symbols['pk_hybrid_rt_cookie'],4),'big')==0x504b4852
    boot_helper=bytes(boot.uc.mem_read(actual_address,len(actual)))
    boot_detour=bytes(boot.uc.mem_read(site,len(detour)))
    assert boot_helper==actual,'boot loader helper readback differs from final ELF'
    assert boot_detour==detour,'booted detour differs from packaged MAIN'
    paths=[Path(__file__).resolve(),source,proof_path,standalone,image,elf,build/'BUILD.json',ROOT/'out/raw/section_3_MAIN_OS.bin',
           original_binary,proof_path.parent/'kernel.nm',reconstructed,execution_path,replay/'costs.csv',*map(Path,replay_inputs)]
    report=dict(status='PASS_FINAL_IMAGE_STOCK_MIXER_PROOF_AND_BOOT_BINDING',
                version=metadata['version'],source_commit=metadata.get('source_commit'),
                image_sha256=sha(image),elf_sha256=sha(elf),proof_sha256=sha(proof_path),
                standalone_cases=proof['cases'],same_image_cycle_controls=True,
                linked_candidate=True,
                helper=dict(name=name,standalone_address=standalone_address,linked_address=actual_address,
                            bytes=len(actual),sha256=hashlib.sha256(actual).hexdigest(),
                            linked_equals_proven=True,boot_readback_equals_linked=True),
                detour=dict(address=site,bytes=len(detour),sha256=hashlib.sha256(detour).hexdigest(),
                            packaged_and_booted_match=True,padding='one NOP'),
                original_stock_remainder_unchanged=True,
                executed_binary_binding=dict(full_binary_equals_pinned_ELF_objcopy=True,
                                             loaded_helper_equals_pinned_ELF_symbol=True,
                                             symbols_equal_pinned_ELF_nm=True),
                replay=dict(status=execution['status'],cases=execution['cases'],
                            command=command,inputs=replay_inputs,inputs_unchanged_after_execution=True,
                            output_path=str(execution_path),output_sha256=sha(execution_path),
                            same_image_cycle_controls=True),
                standalone_mean_saved_cycles=proof['mean_saved_cycles'],
                standalone_mean_saved_us=proof['mean_saved_us_per_block'],
                source_sha256={str(p):sha(p) for p in paths},
                limits=['Binds the exact complete-block register/CCR/EMAC/aliased-memory proof to final packaged and booted code.',
                        'The boot readback does not establish full-workload timing, lifecycle qualification or physical hardware acceptance.'])
    (work/'BINDING.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
