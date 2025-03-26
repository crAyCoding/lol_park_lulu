import sqlite3
import discord

matches_db = f"/database/matches.db"


# 총 게임 수 가져오기
def get_total_games():
    conn = sqlite3.connect(matches_db)
    cursor = conn.cursor()

    query = "SELECT COUNT(*) FROM GAMES;"
    cursor.execute(query)
    total_games = cursor.fetchone()[0]

    conn.close()
    return total_games


# 라인별 챔피언 승률 가져오기
def get_champions_by_lane_with_winrate(summoner_id):
    conn = sqlite3.connect(matches_db)
    cursor = conn.cursor()

    query = '''
    WITH PlayerGames AS (
        SELECT P.line, P.champion, P.team_name, G.winner_team
        FROM PICKS P
        JOIN GAMES G
        ON P.match_id = G.match_id AND P.game_index = G.game_index
        WHERE P.summoner_id = ?
    )
    SELECT 
        line,
        champion,
        COUNT(*) AS total_games,
        SUM(CASE WHEN team_name = winner_team THEN 1 ELSE 0 END) AS wins,
        SUM(CASE WHEN team_name != winner_team THEN 1 ELSE 0 END) AS loses,
        ROUND(
            (SUM(CASE WHEN team_name = winner_team THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(*), 0), 
            2
        ) AS win_rate
    FROM PlayerGames
    GROUP BY line, champion
    ORDER BY 
        CASE 
            WHEN line = 'top' THEN 1
            WHEN line = 'jungle' THEN 2
            WHEN line = 'mid' THEN 3
            WHEN line = 'bot' THEN 4
            WHEN line = 'support' THEN 5
        END,
        total_games DESC;
    '''

    cursor.execute(query, (summoner_id,))
    result = cursor.fetchall()  # [(line, champion, total_games, wins, loses, win_rate), ...]

    conn.close()

    # 변환: {라인: [{champion, total_games, wins, loses, win_rate}]}
    lane_stats = {}
    for row in result:
        line, champion, total_games, wins, loses, win_rate = row
        if line not in lane_stats:
            lane_stats[line] = []
        lane_stats[line].append({
            "champion": champion,
            "total_games": total_games,
            "wins": wins,
            "loses": loses,
            "win_rate": win_rate
        })

    return lane_stats


# 채널별 승,패 승률 가져오기
def get_summoner_stats_by_channel(member: discord.member):
    
    summoner_id = member.id

    conn = sqlite3.connect(matches_db)
    cursor = conn.cursor()

    query = '''
    WITH PlayerGames AS (
        SELECT M.channel, P.team_name, G.winner_team
        FROM PICKS P
        JOIN GAMES G
        ON P.match_id = G.match_id AND P.game_index = G.game_index
        JOIN MATCHES M
        ON P.match_id = M.match_id
        WHERE P.summoner_id = ?
    )
    SELECT 
        channel,
        COUNT(*) AS total_games,
        SUM(CASE WHEN team_name = winner_team THEN 1 ELSE 0 END) AS wins,
        SUM(CASE WHEN team_name != winner_team THEN 1 ELSE 0 END) AS loses,
        ROUND(
            (SUM(CASE WHEN team_name = winner_team THEN 1 ELSE 0 END) * 100.0) / 
            NULLIF(COUNT(*), 0), 
            2
        ) AS win_rate
    FROM PlayerGames
    GROUP BY channel
    ORDER BY channel ASC;
    '''

    cursor.execute(query, (summoner_id,))
    result = cursor.fetchall()  # [(channel, total_games, wins, loses, win_rate), ...]

    conn.close()

    return {
        row[0]: {
            "total_games": row[1],
            "wins": row[2],
            "loses": row[3],
            "win_rate": row[4]
        }
        for row in result
    }


# 전체 게임 밴 리스트 불러오기
def get_most_banned_champions():
    conn = sqlite3.connect(matches_db)
    cursor = conn.cursor()

    query = '''
    SELECT champion, COUNT(*) AS ban_count
    FROM BANS
    GROUP BY champion
    ORDER BY ban_count DESC;
    '''

    cursor.execute(query)
    result = cursor.fetchall()  # [(champion, ban_count), ...]

    conn.close()

    return [{"champion": row[0], "ban_count": row[1]} for row in result]


# 유저별 라인별로 밴 당한 챔피언 목록
def get_banned_champions_by_position(summoner_id):
    conn = sqlite3.connect(matches_db)
    cursor = conn.cursor()

    query = '''
    WITH PlayerGames AS (
        SELECT P.match_id, P.game_index, P.line,
            CASE WHEN P.team_name = 'team_1' THEN 'team_2'
                WHEN P.team_name = 'team_2' THEN 'team_1' 
            END AS opposite_team
        FROM PICKS P
        WHERE P.summoner_id = ?
    ),
    LaneGames AS (
        SELECT line, COUNT(DISTINCT match_id || '-' || game_index) AS total_games
        FROM PlayerGames
        GROUP BY line
    ),
    FixedOrder AS (
        -- 강제적으로 정렬된 라인 순서 유지
        SELECT 'top' AS position, 0 AS sort_order UNION ALL
        SELECT 'jungle', 1 UNION ALL
        SELECT 'mid', 2 UNION ALL
        SELECT 'bot', 3 UNION ALL
        SELECT 'support', 4
    )
    -- 먼저 각 라인별 플레이한 게임 수를 고정된 순서로 출력
    SELECT 
        FO.position, 'Total Games' AS champion, 
        COALESCE(LG.total_games, 0) AS ban_count, 
        FO.sort_order
    FROM FixedOrder FO
    LEFT JOIN LaneGames LG ON FO.position = LG.line

    UNION ALL

    -- 이후 각 라인에서 반대팀이 BAN한 챔피언 목록 출력
    SELECT 
        PG.line AS position, B.champion, COUNT(*) AS ban_count, 
        (CASE 
            WHEN PG.line = 'top' THEN 0
            WHEN PG.line = 'jungle' THEN 1
            WHEN PG.line = 'mid' THEN 2
            WHEN PG.line = 'bot' THEN 3
            WHEN PG.line = 'support' THEN 4
            ELSE 5
        END) AS sort_order
    FROM BANS B
    JOIN PlayerGames PG
    ON B.match_id = PG.match_id 
    AND B.game_index = PG.game_index
    AND B.team_name = PG.opposite_team
    GROUP BY PG.line, B.champion

    ORDER BY sort_order, ban_count DESC;

    '''

    cursor.execute(query, (summoner_id,))
    result = cursor.fetchall()  # [(position, champion, ban_count), ...]

    conn.close()

    return result


# 모스트 픽 가져오기 (TOP 50)
def get_most_picked_champions():
    conn = sqlite3.connect(matches_db)
    cursor = conn.cursor()

    query = '''
    WITH TotalGames AS (
        SELECT COUNT(*) AS total_games FROM GAMES
    ),
    ChampionPicks AS (
        SELECT P.champion, COUNT(*) AS pick_count
        FROM PICKS P
        GROUP BY P.champion
    )
    SELECT 
        CP.champion, 
        CP.pick_count
    FROM ChampionPicks CP
    ORDER BY CP.pick_count DESC;
    '''

    cursor.execute(query)
    result = cursor.fetchall()

    conn.close()

    return result


# 라인별 픽 한 챔피언 가져오기
def get_picked_champions_by_position(summoner_id):
    conn = sqlite3.connect(matches_db)
    cursor = conn.cursor()

    query = '''
    WITH PlayerGames AS (
        SELECT P.match_id, P.game_index, P.line, P.champion
        FROM PICKS P
        WHERE P.summoner_id = ?
    ),
    LaneGames AS (
        SELECT line, COUNT(DISTINCT match_id || '-' || game_index) AS total_games
        FROM PlayerGames
        GROUP BY line
    ),
    FixedOrder AS (
        SELECT 'top' AS position, 0 AS sort_order UNION ALL
        SELECT 'jungle', 1 UNION ALL
        SELECT 'mid', 2 UNION ALL
        SELECT 'bot', 3 UNION ALL
        SELECT 'support', 4
    )
    -- 각 라인별 플레이한 게임 수를 고정된 순서로 출력
    SELECT 
        FO.position, 'Total Games' AS champion, 
        COALESCE(LG.total_games, 0) AS pick_count, 
        FO.sort_order
    FROM FixedOrder FO
    LEFT JOIN LaneGames LG ON FO.position = LG.line

    UNION ALL

    -- 이후 각 라인에서 픽한 챔피언 목록 출력
    SELECT 
        PG.line AS position, PG.champion, COUNT(*) AS pick_count, 
        (CASE 
            WHEN PG.line = 'top' THEN 0
            WHEN PG.line = 'jungle' THEN 1
            WHEN PG.line = 'mid' THEN 2
            WHEN PG.line = 'bot' THEN 3
            WHEN PG.line = 'support' THEN 4
            ELSE 5
        END) AS sort_order
    FROM PlayerGames PG
    GROUP BY PG.line, PG.champion
    ORDER BY sort_order, pick_count DESC;
    '''

    cursor.execute(query, (summoner_id,))
    result = cursor.fetchall()  # [(position, champion, pick_count), ...]

    conn.close()

    return result



# match_id로 내전에 참여한 소환사들의 id 불러오기
def get_summoners_by_match(match_id):
    conn = sqlite3.connect(matches_db)
    cursor = conn.cursor()

    query = '''
    SELECT DISTINCT summoner_id, team_name 
    FROM PICKS 
    WHERE match_id = ?;
    '''
    
    cursor.execute(query, (match_id,))
    data = cursor.fetchall()
    
    team_1 = [row[0] for row in data if row[1] == 'team_1']
    team_2 = [row[0] for row in data if row[1] == 'team_2']
    
    conn.close()
    return {'team_1': team_1, 'team_2': team_2}


# 모스트 픽 가져오기
def get_most_picked_champions(summoner_id):
    conn = sqlite3.connect(matches_db)
    cursor = conn.cursor()

    query = '''
    WITH PlayerPicks AS (
        SELECT champion, COUNT(*) AS pick_count,
               SUM(CASE WHEN P.team_name = G.winner_team THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN P.team_name != G.winner_team THEN 1 ELSE 0 END) AS losses
        FROM PICKS P
        JOIN GAMES G ON P.match_id = G.match_id AND P.game_index = G.game_index
        WHERE P.summoner_id = ?
        GROUP BY champion
    )
    SELECT champion, pick_count, wins, losses, 
           ROUND((wins * 100.0) / NULLIF(pick_count, 0), 2) AS win_rate
    FROM PlayerPicks
    ORDER BY pick_count DESC, win_rate DESC;
    '''

    cursor.execute(query, (summoner_id,))
    result = cursor.fetchall()  # [(champion, pick_count, wins, losses, win_rate), ...]

    conn.close()

    return result


def get_linewise_game_stats(summoner_id):
    conn = sqlite3.connect(matches_db)
    cursor = conn.cursor()

    query = '''
    WITH LineStats AS (
        SELECT P.line, COUNT(*) AS total_games,
               SUM(CASE WHEN P.team_name = G.winner_team THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN P.team_name != G.winner_team THEN 1 ELSE 0 END) AS losses,
               ROUND((SUM(CASE WHEN P.team_name = G.winner_team THEN 1 ELSE 0 END) * 100.0) / NULLIF(COUNT(*), 0), 2) AS win_rate
        FROM PICKS P
        JOIN GAMES G ON P.match_id = G.match_id AND P.game_index = G.game_index
        WHERE P.summoner_id = ?
        GROUP BY P.line
    )
    SELECT line, total_games, wins, losses, win_rate
    FROM LineStats
    ORDER BY total_games DESC, win_rate DESC;
    '''

    cursor.execute(query, (summoner_id,))
    result = cursor.fetchall()  # [(line, total_games, wins, losses, win_rate), ...]

    conn.close()

    return result