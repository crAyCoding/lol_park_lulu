import os
import discord
from dotenv import load_dotenv
from discord.ext import commands, tasks
from record import *
from functions import *
from magics import *
from bot import bot
from lolpark_premium import lolpark_premium
import datetime
import pytz

# 한국 시간대 설정
korea_timezone = pytz.timezone('Asia/Seoul')

# 테스트 할때 아래 사용
load_dotenv()
# GitHub Secrets에서 가져오는 값
TOKEN = os.getenv('DISCORD_TOKEN')


@tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=korea_timezone))
async def daily_update_total_record():
    import daily

    korea_time = datetime.datetime.now(korea_timezone)
    today_date = korea_time.strftime("%Y년 %m월 %d일")

    await daily.update_lolpark_record_message(date=today_date)


@bot.event
async def on_ready():
    await bot.tree.sync()  # 슬래시 명령어 동기화


@bot.tree.command(name="전적")
async def find_record(interaction: discord.Interaction, member: discord.Member = None):

    import config

    await interaction.response.defer(ephemeral=(interaction.channel_id == config.record_search_channel_private_id))


    channel_id = interaction.channel_id
    user = interaction.user
    user_premium_role = discord.utils.get(user.roles, name='LOLPARK PREMIUM')
    
    if member is None:
        member = interaction.user

    lolpark_standard_role = discord.utils.get(member.roles, name='LOLPARK STANDARD')
    lolpark_premium_role = discord.utils.get(member.roles, name='LOLPARK PREMIUM')
    
    # 프리미엄 프로필 생성 및 전송하는 함수
    async def send_premium_profile():
        profile = await lolpark_premium(member)
        buffer = io.BytesIO()
        profile.save(buffer, format='PNG')
        buffer.seek(0)
        await interaction.followup.send(
            file=discord.File(buffer, filename=f"{member.id}_profile.png")
        )
        
    # 일반 프로필 생성 및 전송하는 함수
    async def send_standard_profile():
        profile_embed = discord.Embed(
            title=f"[ LOLPARK 2025 SPRING SEASON ]",
            description=get_summarized_record_text(member),
            color=discord.Color.pink()
        )
        icon_url = member.avatar.url if member.avatar else member.default_avatar.url
        profile_embed.set_author(name=get_nickname(member), icon_url=icon_url)
        await interaction.followup.send(embed=profile_embed)

    # 관리자 채널: 항상 프리미엄 결과 표시
    if channel_id == config.record_search_channel_administrator_id:
        await send_premium_profile()
    
    # 전적 열람 멤버가 권한이 아예 없는 경우, 무시
    if not lolpark_premium_role and not lolpark_premium_role:
        await interaction.followup.send(f"대상의 전적 열람 권한이 없습니다.", ephemeral=True)
        return
    
    # 공개 채널
    if channel_id == config.record_search_channel_public_id:
        if lolpark_premium_role and user_premium_role:
            await send_premium_profile()
        elif lolpark_premium_role or lolpark_standard_role:
            await send_standard_profile()
            return
    
    # 비공개 채널
    if channel_id == config.record_search_channel_private_id:
        if lolpark_premium_role and user_premium_role:
            await send_premium_profile()
        elif lolpark_premium_role or lolpark_standard_role:
            await send_standard_profile()
            return
    
    # 자신의 전적을 조회한 경우 추가 기능 버튼 제공
    if member == user:
        class PremiumView(discord.ui.View):
            def __init__(self, member):
                super().__init__(timeout=180)
                self.message = None
                self.member = member
                self.add_item(MostPickButton())
                self.add_item(MostBannedButton())

            async def on_timeout(self):
                try:
                    await self.message.delete()
                except discord.NotFound:
                    pass
                except Exception as e:
                    print(f"오류 발생 : {e}")

        class MostPickButton(discord.ui.Button):
            def __init__(self):
                super().__init__(label="가장 많이 픽한 챔피언", style=discord.ButtonStyle.primary)
            
            async def callback(self, interaction):
                view = self.view
                await interaction.response.send_message(get_picked_by_lane_text(view.member), ephemeral=True)

        class MostBannedButton(discord.ui.Button):
            def __init__(self):
                super().__init__(label="가장 많이 밴한 챔피언", style=discord.ButtonStyle.danger)
            
            async def callback(self, interaction):
                view = self.view
                await interaction.response.send_message(get_banned_by_lane_text(view.member), ephemeral=True)

        premium_view = PremiumView(member)
        premium_view.message = await interaction.followup.send(
            content="## 롤파크 프리미엄 추가 기능", 
            view=premium_view,
            ephemeral=True
        )


@bot.command()
@commands.has_role("LOLPARK PREMIUM")
async def 상세전적(ctx):    

    member = ctx.author

    profile = await lolpark_premium(member)

    buffer = io.BytesIO()
    profile.save(buffer, format='PNG')
    buffer.seek(0)

    await ctx.send(file=discord.File(buffer, filename=f"{member.id}_profile.png"))


@bot.command()
@commands.is_owner()
async def 기록삭제(ctx, match_id: int):

    try:
        delete_match_data(match_id)
        await ctx.send(f'{match_id}번 내전 기록을 삭제했습니다.')
    except Exception as e:
        await ctx.send(f'기록 삭제 중 오류가 발생했습니다.')


@bot.command()
@commands.has_role("관리자")
async def 내전정보(ctx, match_id: int):

    match_summoner_ids = get_summoners_by_match(match_id)

    lolpark = bot.get_guild(1287065134652457020)

    match_text = f'## 내전 #{match_id}에 참여한 소환사 목록입니다.\n\n'

    match_text += f'### 1팀\n\n'
    for id in match_summoner_ids['team_1']:
        match_text += f'{get_nickname(lolpark.get_member(id))}\n'
    
    match_text += f'\n### 2팀\n\n'
    for id in match_summoner_ids['team_2']:
        match_text += f'{get_nickname(lolpark.get_member(id))}\n'

    await ctx.send(match_text)


@bot.command()
@commands.is_owner()
async def 승패변경(ctx, match_id: int, game_number: int):
    import magics 

    if magics.swap_game_winner(match_id, game_number):
        await ctx.send(f"내전 #{match_id} {game_number}번 게임 결과가 수정되었습니다.")


@bot.command()
@commands.is_owner()
async def 죽어라마술사(ctx):
    await ctx.send("아.")
    await bot.close()


@bot.command()
@commands.is_owner()
async def 테스트(ctx):
    return


# 명령어 에러 처리
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"Unhandled error: {error}")


def main() -> None:
    bot.run(token=TOKEN)


if __name__ == '__main__':
    main()
