"""LUNA VEIL リール7本の台本データ。

テロップ行の書き方:
  "h:..." 見出し（大）  "m:..." 本文  "s:..." 小さい補足  "n:..." カウントダウン数字
  "r:星座|石|キーワード" 一覧の1行  先頭に "_" を付けると場所だけ確保して非表示（積み上げ表示用）
  {g:...} 金  {b:...} 青  {p:...} 紫  {o:...} オレンジ
"""


def T(at, lines, y=None, orn=False, fi=None, stack=False, cta=False):
    return dict(at=at, lines=lines, y=y, orn=orn, fi=fi, stack=stack, cta=cta)


def cut(dur, scene, motion, telops, **kw):
    return dict(dur=dur, scene=scene, motion=motion, telops=telops, **kw)


# 画像差し替え用の英語プロンプト（R11と同じ写実シネマ調）。シーン名ごとの既定文。
PROMPT_HEAD = (
    "Photorealistic cinematic vertical 9:16 image (1080x1920) for a fortune-telling and\n"
    "power-stone brand Instagram reel."
)
PROMPT_TAIL = (
    "Keep the center area dark and empty as negative space for caption text.\n"
    "Absolutely no text, no letters, no numbers, no watermark, no logo."
)
SCENE_PROMPTS = {
    "new_moon_sky": "A barely visible new moon, only a faint thin rim of light, in a deep purple-black\n"
    "starry night sky with a soft band of the Milky Way. A faint warm golden glow on the horizon.\n"
    "Quiet, mysterious, luxurious mood, deep purple and black tones, tiny golden dust particles.",
    "night_window": "An occult altar by an arched night window. Outside the window, a thin crescent moon\n"
    "and a starry sky with pale blue moonlight streaming in. On a dark wooden table in the foreground,\n"
    "a purple candle in a brass holder and a small quartz crystal cluster. Deep purple and black tones,\n"
    "faint golden dust particles in the air, shallow depth of field.",
    "wish_paper": "A folded cream paper with a handwritten wish (handwriting blurred and illegible) on a dark\n"
    "wooden table, a clear quartz crystal point placed on the paper, a lit candle softly out of focus\n"
    "in the background. Warm candlelight mixed with pale blue moonlight, deep purple tones,\n"
    "shallow depth of field.",
    "wish_paper_bracelet": "A folded cream paper with a handwritten wish (handwriting blurred and illegible) on a\n"
    "dark wooden table, a power-stone bead bracelet resting on top of the paper, a lit candle softly\n"
    "out of focus in the background. Warm candlelight, deep purple tones, shallow depth of field.",
    "gold_altar": "A mystical altar bathed in warm golden candlelight. A glowing golden citrine crystal\n"
    "cluster, a small stack of gold coins, a lit golden candle, brass ornaments, deep purple velvet\n"
    "cloth. Symbolizing abundance and money luck. Warm gold and deep purple tones, floating golden\n"
    "dust, shallow depth of field.",
    "gold_altar_orange": "A mystical altar in warm candlelight with glowing orange carnelian and sunstone crystals\n"
    "and soft beige stones on deep purple velvet. Warm orange, beige and deep purple tones, floating\n"
    "golden dust, shallow depth of field.",
    "crystal_altar": "A deep purple amethyst crystal cluster glowing softly on a dark altar, a lit candle\n"
    "in the background, deep purple and black tones, floating golden dust, shallow depth of field.",
    "bracelet": "A luxurious power-stone bead bracelet (amethyst, clear quartz and golden citrine beads)\n"
    "resting on deep purple velvet, seen from a slightly high angle, lit by a candle on the left,\n"
    "floating golden dust particles, deep purple and black tones, shallow depth of field.",
    "bracelet_gold": "A bead bracelet of golden citrine and tiger's eye beads on deep purple velvet, warm\n"
    "golden candlelight glowing inside the beads, floating golden dust, luxurious and warm,\n"
    "shallow depth of field.",
    "bracelet_orange": "A bead bracelet of orange carnelian, sunstone and soft beige moonstone beads on warm\n"
    "dark velvet, gentle candlelight, floating golden dust, warm and calm, shallow depth of field.",
    "bracelet_pair": "Two power-stone bead bracelets side by side on deep purple velvet: a purple amethyst\n"
    "bracelet on the LEFT and an orange carnelian bracelet on the RIGHT, soft candlelight, deep purple\n"
    "and black tones, shallow depth of field.",
    "golden_sky": "Soft golden light rays falling from above through a deep purple night sky, filled with\n"
    "floating golden bokeh and sparkling dust, dreamy and luxurious, symbolizing receiving abundance.",
    "torii_glow": "A silhouette of a Japanese shrine torii gate at night, backlit by a warm golden glow,\n"
    "thin mist on the ground, starry deep purple sky, sacred and calm atmosphere.",
    "full_moon": "A large bright full moon in a deep blue-purple night sky, soft moonlit clouds below it,\n"
    "sparkling stars, serene, mystical and luxurious.",
    "moon_window": "Power stones (an amethyst cluster, a clear quartz point and a bead bracelet) placed on a\n"
    "windowsill, bathed in pale blue light from a large full moon seen through an arched window.\n"
    "Quiet, purifying atmosphere, deep blue and purple tones, shallow depth of field.",
    "two_stones": "A barely visible new moon in a deep starry night sky. On a dark altar in the foreground,\n"
    "a glowing golden gemstone on the LEFT and a cool blue gemstone on the RIGHT, placed as a symbolic\n"
    "pair representing two choices. Deep purple and black tones, faint floating light particles,\n"
    "shallow depth of field.",
    "blue_window": "A night windowsill lit by pale blue moonlight. A clear glass of water, a folded white\n"
    "paper, and a clear quartz crystal. Cool blue and deep purple tones, quiet and serene,\n"
    "symbolizing letting go and cleansing, shallow depth of field.",
    "zodiac_wheel": "An elegant thin golden astrological wheel made only of abstract circles, lines and dots\n"
    "(NO zodiac symbols, NO letters) faintly glowing in a deep navy-purple starry sky, mystical and\n"
    "luxurious.",
    "dawn_rays": "A majestic sunrise on the horizon with golden light rays spreading upward through soft\n"
    "clouds, deep purple sky above turning to gold, sacred and hopeful mood.",
}


REELS = [
    dict(
        id="01",
        slug="shingetsu-1011",
        title="10/11 新月×一粒万倍日「この日だけはやって」",
        post="10/8（木）〜10/9（金）",
        why="開運日×金運は同ジャンルで保存5,000超・最大380万再生。R11（引き寄せと手放しの予告回）の本編にもなる。",
        seed=11,
        chords="D",
        cuts=[
            cut(3.4, "new_moon_sky", "in", [
                T(0, ["s:10月11日（日）", "h:{g:新月 × 一粒万倍日}", "m:この日だけは", "m:やってほしいことがある"], orn=True),
            ]),
            cut(3.6, "night_window", "left", [
                T(0, ["m:天秤座の新月のテーマは", "h:{g:調和} と {g:ご縁}"]),
            ]),
            cut(4.8, "wish_paper", "in", [
                T(0, ["m:願いは “〜したい” ではなく", "h:{g:“〜しました”}", "m:と完了形で書く"]),
                T(2.5, ["s:書くのは", "m:{g:11日 0:50} の新月から", "m:48時間以内に"]),
            ]),
            cut(3.6, "wish_paper_bracelet", "right", [
                T(0, ["m:書いた紙の上に", "h:{g:水晶やブレスレット}を", "m:ひと晩のせておく"]),
            ]),
            cut(3.6, "gold_altar", "in", [
                T(0, ["m:一粒万倍日に始めたことは", "h:{g:万倍に育つ}", "s:と言われています"]),
            ]),
            cut(3.4, "bracelet", "in", [
                T(0, ["h:{g:保存して}", "m:11日の夜に見返してね"], cta=True),
            ]),
        ],
        caption="""10月11日（日）は、新月×一粒万倍日🌑

天秤座の新月のテーマは「調和」と「人とのご縁」。
願いは「〜したい」ではなく「〜しました」と完了形で書くのがポイントです。

✦ 書くタイミング：11日 0:50の新月から48時間以内
✦ 書いた紙の上に、水晶やブレスレットをひと晩のせて
✦ 一粒万倍日に始めたことは、万倍に育つと言われています

忘れないように【保存】して、11日の夜に見返してね🌙""",
        tags=["#新月", "#一粒万倍日", "#新月の願い事", "#パワーストーン", "#引き寄せの法則"],
    ),
    dict(
        id="02",
        slug="tsuchinotomi-1022",
        title="10/22 己巳の日「60日に1度の金運日」",
        post="10/19（月）〜10/20（火）",
        why="金運は同ジャンルで最大380万再生・188万再生のテーマ。「受け取ります」コメント型はここだけで使う。",
        seed=22,
        chords="F",
        cuts=[
            cut(3.4, "gold_altar", "in", [
                T(0, ["s:10月22日（木）", "h:{g:60日に1度の}", "h:{g:金運日}", "m:己巳（つちのとみ）の日"], orn=True),
            ]),
            cut(3.4, "golden_sky", "up", [
                T(0, ["m:この動画が流れてきたなら", "h:{g:受け取る準備が}", "h:{g:できたサイン}"]),
            ]),
            cut(3.6, "torii_glow", "in", [
                T(0, ["m:己巳の日は", "m:金運と芸術の神さま", "h:{g:弁財天さま}", "m:のご縁日"]),
            ]),
            cut(4.4, "gold_altar", "left", [
                T(0, ["m:この日にやりたい3つ", "_m:① お財布の中を整える", "_m:② 弁財天さまにお参り", "_m:③ {g:黄金の石}を身につける"]),
                T(0.9, ["m:この日にやりたい3つ", "m:① お財布の中を整える", "_m:② 弁財天さまにお参り", "_m:③ {g:黄金の石}を身につける"], stack=True),
                T(1.9, ["m:この日にやりたい3つ", "m:① お財布の中を整える", "m:② 弁財天さまにお参り", "_m:③ {g:黄金の石}を身につける"], stack=True),
                T(2.9, ["m:この日にやりたい3つ", "m:① お財布の中を整える", "m:② 弁財天さまにお参り", "m:③ {g:黄金の石}を身につける"], stack=True),
            ]),
            cut(4.0, "bracelet_gold", "in", [
                T(0, ["h:{g:シトリン}", "s:豊かさを呼ぶ “商人の石”", "h:{g:タイガーアイ}", "s:金運と決断力のお守り"]),
            ]),
            cut(3.6, "golden_sky", "in", [
                T(0, ["m:受け取る方は", "m:コメントに", "h:{g:「受け取ります」}"], cta=True),
            ]),
        ],
        caption="""10月22日（木）は、60日に1度の金運日「己巳（つちのとみ）の日」✨

己巳の日は、金運と芸術の神さま・弁財天さまのご縁日。
この動画が流れてきたなら、受け取る準備ができたサインかもしれません。

この日にやりたい3つ
① お財布の中を整える
② 弁財天さまにお参り
③ 黄金の石を身につける（シトリン・タイガーアイ）

受け取る方は、コメントに「受け取ります」と残してね🌙""",
        tags=["#己巳の日", "#金運アップ", "#弁財天", "#パワーストーン", "#開運日"],
    ),
    dict(
        id="03",
        slug="mangetsu-1026",
        title="10/26 牡牛座の満月×一粒万倍日「石を持ってる人は絶対やって」",
        post="10/23（金）〜10/24（土）",
        why="開運日ネタ＋石を持っている今のお客さんに刺さる。浄化の流れでブレスレットに自然につなげられる。",
        seed=26,
        chords="E",
        cuts=[
            cut(3.6, "full_moon", "in", [
                T(0, ["s:パワーストーンを持っている人へ", "h:{g:10月26日（月）}", "h:の満月は", "h:絶対にやって"], y=1080, orn=True),
            ]),
            cut(3.6, "moon_window", "left", [
                T(0, ["m:満月の夜は", "h:石の{g:浄化}と{g:充電}に", "m:いちばんのタイミング"]),
            ]),
            cut(4.2, "gold_altar", "in", [
                T(0, ["m:しかも今回は", "h:{g:牡牛座の満月}", "h:× {g:一粒万倍日}", "s:牡牛座は “豊かさ” と “お金” の星座"]),
            ]),
            cut(5.0, "moon_window", "in", [
                T(0, ["m:やり方はかんたん", "h:{g:夜、窓辺に置いて}", "h:{g:朝しまうだけ}"]),
                T(2.7, ["m:月の光は", "h:どの石にもやさしい", "s:日光で色あせる石も、月光なら安心"]),
            ]),
            cut(3.6, "bracelet", "in", [
                T(0, ["m:浄化した石を", "m:一粒万倍日から", "h:{g:新しく身につける}", "s:のもおすすめ"]),
            ]),
            cut(3.4, "full_moon", "out", [
                T(0, ["h:{g:保存して}", "m:26日の夜、月の光をあてよう"], y=1080, cta=True),
            ]),
        ],
        caption="""パワーストーンを持っている人へ🌕

10月26日（月）は、牡牛座の満月×一粒万倍日。
満月の夜は、石の浄化と充電にいちばんのタイミングです。

✦ やり方：夜、窓辺に石を置いて、朝しまうだけ
✦ 月の光は、日光で色あせやすい石にもやさしい
✦ 浄化した石を、一粒万倍日から新しく身につけ始めるのもおすすめ

牡牛座は「豊かさ」と「お金」の星座。
【保存】して、26日の夜に月の光をあててあげてね。""",
        tags=["#満月", "#パワーストーン浄化", "#一粒万倍日", "#パワーストーン", "#牡牛座満月"],
    ),
    dict(
        id="04",
        slug="kin-ka-ao",
        title="金と青、直感でどっち？（参加型）",
        post="10/9（金）前後（①の新月とセットで）",
        why="「あなたはどっち？」の参加型はコメントが伸びる。188万再生アカウントと同じコメント→DMの流れが作れる。R11の金/青の世界観をそのまま使える。",
        seed=4,
        chords="A",
        cuts=[
            cut(5.6, "two_stones", "in", [
                T(0, ["h:直感で選んで", "m:{g:金} と {b:青}、どっち？"], y=720, orn=True),
                T(3.0, ["n:{g:3}"], y=760, fi=0.06),
                T(3.85, ["n:{g:2}"], y=760, fi=0.06),
                T(4.7, ["n:{g:1}"], y=760, fi=0.06),
            ]),
            cut(4.0, "gold_altar", "in", [
                T(0, ["h:{g:金}を選んだあなた", "m:今は “{g:引き寄せる}” 時期", "s:始めること・受け取ることに追い風"]),
            ]),
            cut(4.0, "blue_window", "in", [
                T(0, ["h:{b:青}を選んだあなた", "m:今は “{b:手放す}” 時期", "s:整理と浄化で、次の運が入る場所をつくる"]),
            ]),
            cut(4.4, "new_moon_sky", "up", [
                T(0, ["m:10月11日の新月は", "m:{g:金}の人は “迎えました”", "m:{b:青}の人は “手放しました”", "s:と完了形で書いてみて"]),
            ]),
            cut(3.6, "two_stones", "out", [
                T(0, ["m:あなたはどっちだった？", "h:コメントに", "h:“{g:金}” か “{b:青}”"], y=720, cta=True),
            ]),
        ],
        caption="""直感で選んでください。金と青、どっち？🌙

金を選んだあなた → 今は「引き寄せる」時期。始めること・受け取ることに追い風。
青を選んだあなた → 今は「手放す」時期。整理と浄化で、次の運が入る場所をつくるとき。

10月11日の新月は、
金の人は「〜を迎えました」
青の人は「〜を手放しました」
と完了形で書いてみてね。

あなたはどっちだった？コメントに「金」か「青」で教えてね✦""",
        tags=["#新月", "#直感", "#パワーストーン", "#引き寄せの法則", "#手放し"],
    ),
    dict(
        id="05",
        slug="ishi-no-kumiawase",
        title="その2つの石、一緒につけてない？",
        post="いつでも（開運日リールの合間に）",
        why="「一緒にしちゃいけない石」は海外クリスタル界隈の定番バズネタで、日本でも相性NG記事が大量＝検索需要大。「絶対NGはない」で締めて信頼感で差をつける。",
        seed=5,
        chords="C",
        cuts=[
            cut(3.4, "bracelet_pair", "in", [
                T(0, ["h:その2つの石", "h:一緒につけてない？", "s:ブレスレットの組み合わせ、見直して"], orn=True),
            ]),
            cut(4.0, "bracelet_pair", "left", [
                T(0, ["m:“落ち着かせる石” と", "m:“気持ちを高める石” は", "h:{g:意図がぶつかりやすい}", "s:と言われています"]),
            ]),
            cut(4.0, "bracelet_pair", "in", [
                T(0, ["m:たとえば", "h:{p:アメジスト}", "s:癒やし・鎮静", "m:×", "h:{o:カーネリアン}", "s:活力・行動"]),
            ]),
            cut(3.6, "night_window", "in", [
                T(0, ["m:でも実は", "h:“{g:絶対にNG}” な", "h:組み合わせはありません"]),
            ]),
            cut(4.2, "crystal_altar", "in", [
                T(0, ["m:大切なのは、何を叶えたいか", "h:{g:願いの軸を1つ}決めて", "m:それに合う石でまとめること"]),
            ]),
            cut(3.4, "bracelet", "in", [
                T(0, ["m:あなたの組み合わせは？", "h:コメントで", "h:{g:石の名前}を教えてね"], cta=True),
            ]),
        ],
        caption="""そのブレスレット、一緒につけている石を見直してみて💎

“落ち着かせる石”と“気持ちを高める石”は、意図がぶつかりやすいと言われています。
たとえば、アメジスト（癒やし・鎮静）× カーネリアン（活力・行動）。

でも実は、「絶対にNG」な組み合わせはありません。
大切なのは、何を叶えたいか。
願いの軸を1つ決めて、それに合う石でまとめることです。

あなたのブレスレットの組み合わせは？
コメントで石の名前を教えてね🌙""",
        tags=["#パワーストーン", "#パワーストーンブレスレット", "#天然石", "#クリスタル", "#アメジスト"],
    ),
    dict(
        id="06",
        slug="seiza-2027",
        title="星座別「2027年にあなたを守る石」（スクショ保存型）",
        post="11月下旬（来年の運勢の需要が高まる時期）",
        why="星座占いは占いジャンルの人気1位。12星座を1画面にまとめてスクショ・保存・DM送信を狙う。",
        seed=27,
        chords="G",
        cuts=[
            cut(3.4, "zodiac_wheel", "in", [
                T(0, ["s:2027年 丁未（ひのとひつじ）", "h:星座別", "h:{g:あなたを守る石}", "s:スクショして保存してね"], orn=True),
            ]),
            cut(10.0, "zodiac_wheel_dim", "slow", [
                T(0, [
                    "r:牡羊座|カーネリアン|行動力",
                    "r:牡牛座|ローズクォーツ|愛と豊かさ",
                    "r:双子座|シトリン|伝える力",
                    "r:蟹座|ムーンストーン|安らぎ",
                    "r:獅子座|サンストーン|自信",
                    "r:乙女座|アマゾナイト|心の整理",
                ], fi=0.2),
                T(5.0, [
                    "r:天秤座|ペリドット|調和",
                    "r:蠍座|ガーネット|絆",
                    "r:射手座|ターコイズ|守護",
                    "r:山羊座|オニキス|継続",
                    "r:水瓶座|アメジスト|直感",
                    "r:魚座|アクアマリン|癒やし",
                ], fi=0.2),
            ]),
            cut(3.8, "gold_altar_orange", "in", [
                T(0, ["m:2027年のラッキーカラーは", "h:{o:オレンジ} と {o:ベージュ}", "s:と言われています"]),
            ]),
            cut(4.0, "bracelet_orange", "in", [
                T(0, ["m:迷ったら", "h:{o:カーネリアン}を1粒", "m:お守りに", "s:穏やかな火のエネルギーで、願いをじっくり育てる"]),
            ]),
            cut(3.4, "zodiac_wheel", "out", [
                T(0, ["h:{g:スクショ}して", "m:来年のお守りに", "s:大切な人にも送ってあげてね"], cta=True),
            ]),
        ],
        caption="""2027年、星座別にあなたを守る石✦
スクショして、来年のお守りにしてね。

牡羊座　カーネリアン（行動力）
牡牛座　ローズクォーツ（愛と豊かさ）
双子座　シトリン（伝える力）
蟹座　　ムーンストーン（安らぎ）
獅子座　サンストーン（自信）
乙女座　アマゾナイト（心の整理）
天秤座　ペリドット（調和）
蠍座　　ガーネット（絆）
射手座　ターコイズ（守護）
山羊座　オニキス（継続）
水瓶座　アメジスト（直感）
魚座　　アクアマリン（癒やし）

2027年は丁未（ひのとひつじ）。ラッキーカラーはオレンジとベージュと言われています。
迷ったら、カーネリアンを1粒お守りに🌙

大切な人にも送ってあげてね。""",
        tags=["#星座占い", "#2027年", "#パワーストーン", "#守護石", "#星読み"],
    ),
    dict(
        id="07",
        slug="saikyo-1216",
        title="12/16 今年最後の最強開運日",
        post="12/13（日）〜12/14（月）",
        why="開運日×金運の型。天赦日×一粒万倍日は今年4回だけ。年末のギフト需要と重なり、ブレスレットを迎えるきっかけにしやすい。",
        seed=16,
        chords="D",
        cuts=[
            cut(3.6, "dawn_rays", "in", [
                T(0, ["s:2026年、最後の", "h:{g:最強開運日}", "h:12月16日（水）"], orn=True),
            ]),
            cut(4.0, "golden_sky", "up", [
                T(0, ["h:{g:天赦日} × {g:一粒万倍日}", "m:今年この2つが重なるのは", "s:3/5・7/19・10/1・12/16", "m:の4回だけ"]),
            ]),
            cut(4.2, "torii_glow", "in", [
                T(0, ["h:{g:天赦日}", "s:天がすべてを赦す日", "h:{g:一粒万倍日}", "s:始めたことが万倍に育つ日"]),
            ]),
            cut(4.4, "gold_altar", "left", [
                T(0, ["m:この日にやりたいこと", "_m:① 新しいことを始める", "_m:② お財布・お守りを新しくする", "_m:③ 来年の願いを書く"]),
                T(0.9, ["m:この日にやりたいこと", "m:① 新しいことを始める", "_m:② お財布・お守りを新しくする", "_m:③ 来年の願いを書く"], stack=True),
                T(1.9, ["m:この日にやりたいこと", "m:① 新しいことを始める", "m:② お財布・お守りを新しくする", "_m:③ 来年の願いを書く"], stack=True),
                T(2.9, ["m:この日にやりたいこと", "m:① 新しいことを始める", "m:② お財布・お守りを新しくする", "m:③ 来年の願いを書く"], stack=True),
            ]),
            cut(3.6, "bracelet", "in", [
                T(0, ["m:新しいお守り石を", "m:迎えるなら", "h:{g:この日}に"]),
            ]),
            cut(3.4, "dawn_rays", "out", [
                T(0, ["h:{g:保存して}", "m:12月16日に見返してね"], cta=True),
            ]),
        ],
        caption="""2026年、最後の最強開運日は12月16日（水）✨

天赦日 × 一粒万倍日。
今年この2つが重なるのは、3/5・7/19・10/1・12/16の4回だけ。

天赦日＝天がすべてを赦す日
一粒万倍日＝始めたことが万倍に育つ日

この日にやりたいこと
① 新しいことを始める
② お財布・お守りを新しくする
③ 来年の願いを書く

新しいお守り石を迎えるなら、この日に🌙
【保存】して、12月16日に見返してね。""",
        tags=["#天赦日", "#一粒万倍日", "#開運日", "#パワーストーン", "#最強開運日"],
    ),
]
