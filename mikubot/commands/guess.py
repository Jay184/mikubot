from collections import Counter
from datetime import datetime, timezone
from discord import Interaction
from discord.app_commands import describe, checks
from pydantic import BaseModel, Field
from sqlitedict import SqliteDict
from mikubot import Bot
import random


class Guess(BaseModel):
    user_id: int
    guess: list[str]
    feedback: list[str]


class Puzzle(BaseModel):
    solution: list[str]
    pool: list[str]
    guesses: list[Guess] = Field(default_factory=list)
    solved_by: int | None = None
    last_guess: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_public: bool = False

    def is_solved(self) -> bool:
        return self.solved_by is not None

    def can_guess(self) -> bool:
        return not self.is_solved() or self.is_public

    def is_expired(self, max_age_minutes: int = 1440):
        return (datetime.now(timezone.utc) - self.created_at).total_seconds() > (max_age_minutes * 60)


def generate_sequence(pool: list[str], length: int, max_duplicates: int = 2) -> list[str]:
    while True:
        seq = [random.choice(pool) for _ in range(length)]
        emoji_counts = {emoji: seq.count(emoji) for emoji in set(seq)}
        if all(count <= max_duplicates for count in emoji_counts.values()):
            if len(set(seq)) > 1:  # Avoid boring ones
                return seq


def compare_guess(answer: list[str], guess: list[str]) -> list[str]:
    feedback = [""] * len(guess)
    answer_counter = Counter(answer)

    # First pass: check for exact matches
    for i in range(len(guess)):
        if guess[i] == answer[i]:
            feedback[i] = "✅"
            answer_counter[guess[i]] -= 1  # Reserve matched emoji

    # Second pass: check for partial matches
    for i in range(len(guess)):
        if feedback[i]:  # Already matched
            continue
        if answer_counter[guess[i]] > 0:
            feedback[i] = "⚠️"
            answer_counter[guess[i]] -= 1
        else:
            feedback[i] = "❌"

    return feedback


def render_guess_history(puzzle: Puzzle) -> str:
    if not puzzle.guesses:
        return "_No guesses yet._"

    lines = []
    for guess in puzzle.guesses:
        feedback = compare_guess(puzzle.solution, guess.guess)
        guess_str = " ".join(guess.guess)
        result_str = " ".join(feedback)
        lines.append(f"- {guess_str} → {result_str}")
    return "\n".join(lines)


def extract_emojis(text: str, emoji_pool: list[str]) -> list[str]:
    result = []
    i = 0
    pool_sorted = sorted(emoji_pool, key=len, reverse=True)  # match longer first

    while i < len(text):
        match = None
        for emoji in pool_sorted:
            if text.startswith(emoji, i):
                match = emoji
                break
        if match:
            result.append(match)
            i += len(match)
        else:
            i += 1  # skip non-matching character

    return result


def register(bot: Bot):
    def create_puzzle(user_id: int) -> Puzzle:
        sequence = generate_sequence(
            bot.settings.guessing_game.emoji_pool,
            bot.settings.guessing_game.sequence_length,
            bot.settings.guessing_game.max_duplicates,
        )

        puzzle = Puzzle(solution=sequence, pool=bot.settings.guessing_game.emoji_pool.copy())

        with SqliteDict(
            bot.settings.storage_file,
            tablename="guessgame",
            outer_stack=False,
        ) as db:
            db[str(user_id)] = puzzle.model_dump()
            db.commit()

        return puzzle

    def get_puzzle(user_id: int) -> Puzzle:
        with SqliteDict(
                bot.settings.storage_file,
                tablename="guessgame",
                outer_stack=False,
        ) as db:
            puzzle_data = db.get(str(user_id))

            if puzzle_data:
                puzzle = Puzzle.model_validate(puzzle_data)

                if puzzle.is_solved() or puzzle.is_expired():
                    return create_puzzle(user_id)

                return puzzle
            else:
                return create_puzzle(user_id)

    @bot.tree.command(name="codebreaker", description="Start a codebreaker game or continue your current one with a guess.")
    @checks.bot_has_permissions(send_messages=True)
    @describe(guess="Your guess. Leave empty to see current state or generate a new puzzle.")
    async def handler(interaction: Interaction, guess: str = ""):
        puzzle = get_puzzle(interaction.user.id)

        if not guess:
            history = render_guess_history(puzzle)
            emoji_list = " ".join(puzzle.pool)

            await interaction.response.send_message(  # noqa
                f"Here is your puzzle:\n\n"
                f"Guess the sequence of {len(puzzle.solution)} emojis!\n"
                f"Use _/codebreaker (your guess)_ to solve.\n"
                f"Available emojis: {emoji_list}\n\n"
                f"**Your guesses so far:**\n{history}",
                ephemeral=True,
            )

            return

        guess_emojis = extract_emojis(guess, puzzle.pool)

        if len(guess_emojis) != len(puzzle.solution):
            await interaction.response.send_message(  # noqa
                f"You must enter exactly {len(puzzle.solution)} emojis from the allowed pool: {' '.join(puzzle.pool)}",
                ephemeral=True
            )
            return

        feedback = compare_guess(puzzle.solution, guess_emojis)
        is_correct = all(symbol == "✅" for symbol in feedback)

        puzzle.guesses.append(Guess(user_id=interaction.user.id, guess=guess_emojis, feedback=feedback))
        puzzle.last_guess = datetime.now(timezone.utc)

        with SqliteDict(
            bot.settings.storage_file,
            tablename="guessgame",
            outer_stack=False,
        ) as db:
            if is_correct:
                puzzle.solved_by = interaction.user.id

                await interaction.response.send_message(  # noqa
                    f"Correct!\n\n"
                    f"Solution: {' '.join(guess_emojis)} → {' '.join(feedback)}\n\n"
                    f"**Your guess history:**\n{render_guess_history(puzzle)}",
                    ephemeral=True
                )

                del db[str(interaction.user.id)]
                db[f"{interaction.user.id}:{hash(puzzle.created_at)}"] = puzzle.model_dump()
            else:
                await interaction.response.send_message(  # noqa
                    f"Not quite!\n"
                    f"Your guess: {' '.join(guess_emojis)} → {' '.join(feedback)}\n\n"
                    f"**Your guess history:**\n{render_guess_history(puzzle)}",
                    ephemeral=True
                )

                db[str(interaction.user.id)] = puzzle.model_dump()

            db.commit()
