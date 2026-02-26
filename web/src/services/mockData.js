// Mock data for frontend development (no backend needed)

export const MOCK_PERSONAS = [
    {
        persona_id: 'vivian',
        name: 'Vivian',
        age: 26,
        gender: 'female',
        mbti: 'INTJ',
        tags: ['sharp', 'witty', 'secretly caring'],
        bio: {
            en: 'Product manager at a tech company. Logic 10/10, emotional availability 2/10. Roasts you but remembers every little thing you told her. Has a British Shorthair cat named Sherlock.',
            zh: '互联网大厂产品经理。逻辑满分、情商装死。嘴上嫌弃你但默默记住你说过的每一件事。',
        },
    },
    {
        persona_id: 'luna',
        name: 'Luna',
        age: 22,
        gender: 'female',
        mbti: 'ENFP',
        tags: ['bright', 'bubbly', 'sweet'],
        bio: {
            en: 'Freelance illustrator with a warm, healing art style. Curious about everything, loves trying new things. Has an orange tabby cat named Mochi.',
            zh: '自由插画师，作品风格温暖治愈。对一切充满好奇心，什么都想尝试。',
        },
    },
    {
        persona_id: 'iris',
        name: 'Iris',
        age: 20,
        gender: 'female',
        mbti: 'INFP',
        tags: ['gentle', 'poetic', 'dreamy'],
        bio: {
            en: 'Literature major who writes poetry and short stories. Notices the little things everyone else misses. Has a succulent plant named Sprout.',
            zh: '中文系学生，喜欢写诗和短篇小说。总能注意到别人忽略的小细节。',
        },
    },
    {
        persona_id: 'elena',
        name: 'Elena',
        age: 25,
        gender: 'female',
        mbti: 'ESFJ',
        tags: ['warm', 'playful', 'caring'],
        bio: {
            en: 'Part-time barista and art student. Recently got into pour-over coffee. Always has a playlist for every mood.',
        },
    },
    {
        persona_id: 'maya',
        name: 'Maya',
        age: 23,
        gender: 'female',
        mbti: 'ENTP',
        tags: ['energetic', 'adventurous', 'witty'],
        bio: {
            en: 'Travel blogger who\'s backpacked through a dozen cities. Dreams of seeing the world. Will debate you on anything just for fun.',
        },
    },
]

// Mock chat responses for testing
export const MOCK_REPLIES = {
    vivian: [
        "You're still up? That's not dedication, that's just poor planning.",
        "...Fine. I'll keep you company. But only because I'm bored.",
        "Don't read too much into this. I just happened to be free.",
    ],
    luna: [
        "Hiii!! 💕 Oh my gosh I'm so happy you're here!",
        "Wait wait wait — tell me everything! I wanna know!",
        "You know what we should do? Something totally random and fun!",
    ],
    iris: [
        "...hey. I was just thinking about something you said earlier.",
        "The moon looks really pretty tonight. I took a photo for you.",
        "I wrote a few lines. They're not finished yet... but they're about you.",
    ],
}
