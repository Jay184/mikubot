from discord import Interaction
from discord.app_commands import describe, checks, choices, Choice, Range
from capstone import Cs as Capstone, CS_ARCH_X86, CS_MODE_64, CS_OPT_SYNTAX_INTEL
from pefile import PE
from mikubot import Bot


def register(bot: Bot):
    def format_bytes(data: bytes, offset: int = 0) -> str:
        lines = []

        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]
            hex_part = ' '.join(f'{b:02X}' for b in chunk)
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            lines.append(f'{(offset + i):08X}  {hex_part:<47}  |{ascii_part}|')

        return '\n'.join(lines)

    @bot.tree.command(name='code', description='Display binary code of MM+.')
    @checks.bot_has_permissions(send_messages=True)
    @checks.has_role(1023036859883999272)
    @describe(
        version='The version of the game.',
        address='The address to start reading.',
        length='The length of the code to read.',
        assembly='If the code should be displayed as assembly code.',
    )
    @choices(version=[
        Choice(name='1.00', value=0),
        Choice(name='1.01', value=1),
        Choice(name='1.02', value=2),
        Choice(name='1.03', value=3),
    ])
    async def handler(interaction: Interaction, version: Choice[int], address: int, length: int = 0x20, assembly: bool = False):
        md = Capstone(CS_ARCH_X86, CS_MODE_64)
        md.syntax = CS_OPT_SYNTAX_INTEL

        length = max(0x10, min(bot.settings.mm_code.max_length, length))

        file_path = bot.settings.mm_code.binaries[version.value]
        pe = PE(file_path, fast_load=True)

        image_base = pe.OPTIONAL_HEADER.ImageBase
        rva = address - image_base
        data = pe.get_data(rva, length)

        if assembly:
            instructions = md.disasm(data, address, length)
            message = '\n'.join(f'{i.address:08X}:  {i.mnemonic} {i.op_str}' for i in instructions)
            await interaction.response.send_message(f'```x86asm\n{message}\n```')  # noqa
        else:
            message = format_bytes(data, address)
            await interaction.response.send_message(f'```properties\n{message}\n```')  # noqa

        pe.close()
