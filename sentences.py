"""
Fill-in-the-blank sentence bank.
Each entry has:
  - sentence: the full Chinese sentence (the target word appears in it)
  - translation: English/Russian gloss to show as hint
  - target: the word being tested (must match char field in HSK_WORDS)

Mix of simple sentences and short dialogue lines.
"""

SENTENCES = [
    # ── HSK 1 ─────────────────────────────────────────────────────────────
    {"sentence":"我爱你。","translation":"I love you.","target":"爱"},
    {"sentence":"我喝水。","translation":"I drink water.","target":"水"},
    {"sentence":"她吃米饭。","translation":"She eats rice.","target":"吃"},
    {"sentence":"我们去学校。","translation":"We go to school.","target":"去"},
    {"sentence":"他是老师。","translation":"He is a teacher.","target":"是"},
    {"sentence":"这本书很好。","translation":"This book is very good.","target":"好"},
    {"sentence":"今天天气很热。","translation":"Today's weather is very hot.","target":"热"},
    {"sentence":"你叫什么名字？","translation":"What is your name?","target":"名字"},
    {"sentence":"我有一只猫。","translation":"I have a cat.","target":"猫"},
    {"sentence":"她是我的朋友。","translation":"She is my friend.","target":"朋友"},
    {"sentence":"这个苹果很甜。","translation":"This apple is very sweet.","target":"苹果"},
    {"sentence":"现在几点？","translation":"What time is it now?","target":"现在"},
    {"sentence":"我住在北京。","translation":"I live in Beijing.","target":"住"},
    {"sentence":"他在看书。","translation":"He is reading a book.","target":"看"},
    {"sentence":"请坐！","translation":"Please sit down!","target":"坐"},
    {"sentence":"我想喝茶。","translation":"I want to drink tea.","target":"想"},
    {"sentence":"她买了一本书。","translation":"She bought a book.","target":"买"},
    {"sentence":"桌子上有杯子。","translation":"There is a cup on the table.","target":"杯子"},
    {"sentence":"你好，我叫李明。","translation":"Hello, my name is Li Ming.","target":"叫"},
    {"sentence":"明天我去医院。","translation":"Tomorrow I'm going to the hospital.","target":"医院"},
    {"sentence":"这里有很多东西。","translation":"There are many things here.","target":"东西"},
    {"sentence":"我认识她。","translation":"I know her.","target":"认识"},
    {"sentence":"他坐飞机去上海。","translation":"He flew to Shanghai.","target":"飞机"},
    {"sentence":"我的女儿很漂亮。","translation":"My daughter is beautiful.","target":"女儿"},
    {"sentence":"今天是星期几？","translation":"What day of the week is today?","target":"星期"},

    # ── HSK 2 ─────────────────────────────────────────────────────────────
    {"sentence":"他比我高。","translation":"He is taller than me.","target":"比"},
    {"sentence":"你会说汉语吗？","translation":"Can you speak Chinese?","target":"说"},
    {"sentence":"我非常喜欢运动。","translation":"I really like sports.","target":"非常"},
    {"sentence":"她已经回来了。","translation":"She has already come back.","target":"已经"},
    {"sentence":"因为下雨，我没去。","translation":"Because it rained, I didn't go.","target":"因为"},
    {"sentence":"他觉得今天很累。","translation":"He feels very tired today.","target":"觉得"},
    {"sentence":"我们一起跑步吧。","translation":"Let's run together.","target":"跑步"},
    {"sentence":"你知道在哪儿吗？","translation":"Do you know where it is?","target":"知道"},
    {"sentence":"我想去旅游。","translation":"I want to travel.","target":"旅游"},
    {"sentence":"考试开始了。","translation":"The exam has started.","target":"考试"},
    {"sentence":"你的手机在桌上。","translation":"Your phone is on the table.","target":"手机"},
    {"sentence":"他找到了工作。","translation":"He found a job.","target":"找"},
    {"sentence":"这件事很重要。","translation":"This matter is very important.","target":"事情"},
    {"sentence":"我每天七点起床。","translation":"I get up at 7 every day.","target":"起床"},
    {"sentence":"她跳舞跳得很好。","translation":"She dances very well.","target":"跳舞"},
    {"sentence":"这里离学校很近。","translation":"This place is very close to school.","target":"近"},
    {"sentence":"请让我进来。","translation":"Please let me in.","target":"让"},
    {"sentence":"他送给我一份礼物。","translation":"He gave me a gift.","target":"送"},
    {"sentence":"虽然很难，但我喜欢。","translation":"Although it's difficult, I like it.","target":"虽然"},
    {"sentence":"我们应该准备好。","translation":"We should be prepared.","target":"准备"},
    {"sentence":"她唱歌唱得很好。","translation":"She sings very well.","target":"唱歌"},
    {"sentence":"他告诉我一个秘密。","translation":"He told me a secret.","target":"告诉"},
    {"sentence":"请问，洗手间在哪里？","translation":"Excuse me, where is the restroom?","target":"问"},
    {"sentence":"我们欢迎你来中国。","translation":"We welcome you to China.","target":"欢迎"},
    {"sentence":"她穿了一件红色的裙子。","translation":"She wore a red dress.","target":"穿"},

    # ── HSK 3 ─────────────────────────────────────────────────────────────
    {"sentence":"他必须完成作业。","translation":"He must finish his homework.","target":"必须"},
    {"sentence":"我们参加了比赛。","translation":"We participated in the competition.","target":"参加"},
    {"sentence":"这个城市很繁华。","translation":"This city is very prosperous.","target":"城市"},
    {"sentence":"她迟到了十分钟。","translation":"She was ten minutes late.","target":"迟到"},
    {"sentence":"我需要锻炼身体。","translation":"I need to exercise.","target":"锻炼"},
    {"sentence":"他的成绩越来越好。","translation":"His grades are getting better and better.","target":"成绩"},
    {"sentence":"这个超市很大。","translation":"This supermarket is very large.","target":"超市"},
    {"sentence":"她当然知道这件事。","translation":"She certainly knows about this matter.","target":"当然"},
    {"sentence":"我担心他的健康。","translation":"I'm worried about his health.","target":"担心"},
    {"sentence":"他打算去北京学习。","translation":"He plans to go to Beijing to study.","target":"打算"},

    # ── Dialogue lines (short exchanges) ──────────────────────────────────
    {"sentence":"A: 你吃饭了吗？B: 我已经吃了。","translation":"A: Have you eaten? B: I've already eaten.","target":"吃"},
    {"sentence":"A: 你去哪里？B: 我去买东西。","translation":"A: Where are you going? B: I'm going shopping.","target":"买"},
    {"sentence":"A: 今天天气怎么样？B: 今天晴天。","translation":"A: How's the weather today? B: It's sunny today.","target":"晴"},
    {"sentence":"A: 你会游泳吗？B: 会，我很喜欢游泳。","translation":"A: Can you swim? B: Yes, I love swimming.","target":"游泳"},
    {"sentence":"A: 你住在哪里？B: 我住在北京。","translation":"A: Where do you live? B: I live in Beijing.","target":"住"},
    {"sentence":"A: 你为什么学汉语？B: 因为我很喜欢中国文化。","translation":"A: Why do you study Chinese? B: Because I love Chinese culture.","target":"为什么"},
    {"sentence":"A: 你忙吗？B: 是的，最近非常忙。","translation":"A: Are you busy? B: Yes, very busy lately.","target":"忙"},
    {"sentence":"A: 这个多少钱？B: 二十块钱。","translation":"A: How much is this? B: Twenty yuan.","target":"钱"},
    {"sentence":"A: 你喜欢什么运动？B: 我喜欢跑步和游泳。","translation":"A: What sports do you like? B: I like running and swimming.","target":"运动"},
    {"sentence":"A: 你的生日是几月几号？B: 我的生日是三月十号。","translation":"A: When is your birthday? B: My birthday is March 10th.","target":"生日"},
    {"sentence":"A: 他在哪里工作？B: 他在一家公司工作。","translation":"A: Where does he work? B: He works at a company.","target":"工作"},
    {"sentence":"A: 你学习汉语多长时间了？B: 我学了两年了。","translation":"A: How long have you been learning Chinese? B: I've been learning for two years.","target":"学习"},
    {"sentence":"A: 你有兄弟姐妹吗？B: 我有一个哥哥和一个妹妹。","translation":"A: Do you have siblings? B: I have an older brother and a younger sister.","target":"哥哥"},
    {"sentence":"A: 你今天怎么来的？B: 我坐地铁来的。","translation":"A: How did you get here today? B: I came by subway.","target":"地铁"},
    {"sentence":"A: 你喜欢吃什么？B: 我喜欢吃面条。","translation":"A: What do you like to eat? B: I like to eat noodles.","target":"面条"},

    # ── HSK 4 ─────────────────────────────────────────────────────────────
    {"sentence":"我们应该保护环境。","translation":"We should protect the environment.","target":"保护"},
    {"sentence":"他成功地完成了任务。","translation":"He successfully completed the task.","target":"成功"},
    {"sentence":"这是我们公司的产品。","translation":"This is our company's product.","target":"产品"},
    {"sentence":"她诚实地回答了问题。","translation":"She answered the question honestly.","target":"诚实"},
    {"sentence":"这个标准很高。","translation":"This standard is very high.","target":"标准"},

    # ── HSK 5 ─────────────────────────────────────────────────────────────
    {"sentence":"我们要避免这种错误。","translation":"We need to avoid this kind of mistake.","target":"避免"},
    {"sentence":"他不断地努力学习。","translation":"He continuously works hard at studying.","target":"不断"},
    {"sentence":"这项政策充分体现了公平原则。","translation":"This policy fully embodies the principle of fairness.","target":"充分"},
    {"sentence":"他们创造了很多财富。","translation":"They created a lot of wealth.","target":"创造"},
    {"sentence":"此外，我们还需要考虑其他因素。","translation":"Besides, we also need to consider other factors.","target":"此外"},
]
