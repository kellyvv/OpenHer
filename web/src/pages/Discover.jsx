import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useMotionValue, useTransform, animate } from 'framer-motion'
import { fetchPersonas } from '../services/api'
import './Discover.css'

// Gradient palette per persona for avatar backgrounds
const GRADIENTS = [
    'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
    'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
    'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
    'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
]

function SwipeCard({ persona, index, onSwipe, isTop, total }) {
    const x = useMotionValue(0)
    const rotate = useTransform(x, [-300, 300], [-18, 18])
    const likeOpacity = useTransform(x, [0, 120], [0, 1])
    const skipOpacity = useTransform(x, [-120, 0], [1, 0])
    const scale = 1 - index * 0.04
    const y = index * 8

    const handleDragEnd = (_, info) => {
        const threshold = 120
        if (info.offset.x > threshold) {
            animate(x, 600, { duration: 0.4, ease: 'easeOut' })
            setTimeout(() => onSwipe('like', persona), 350)
        } else if (info.offset.x < -threshold) {
            animate(x, -600, { duration: 0.4, ease: 'easeOut' })
            setTimeout(() => onSwipe('skip', persona), 350)
        } else {
            animate(x, 0, { type: 'spring', stiffness: 600, damping: 40 })
        }
    }

    const bio = typeof persona.bio === 'object'
        ? (persona.bio.en || persona.bio.zh || '')
        : (persona.bio || '')

    const gradient = GRADIENTS[total % GRADIENTS.length]

    return (
        <motion.div
            className="swipe-card"
            style={{
                x: isTop ? x : 0,
                rotate: isTop ? rotate : 0,
                scale,
                y,
                zIndex: 10 - index,
            }}
            drag={isTop ? 'x' : false}
            dragConstraints={{ left: 0, right: 0 }}
            dragElastic={0.7}
            onDragEnd={handleDragEnd}
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale, opacity: 1 }}
            transition={{ type: 'spring', stiffness: 300, damping: 25 }}
        >
            {/* Avatar area */}
            <div className="card-visual" style={{ background: gradient }}>
                <div className="card-visual-letter">{persona.name?.[0]}</div>
                <div className="card-visual-shimmer" />
            </div>

            {/* Gradient fade overlay */}
            <div className="card-fade" />

            {/* Info overlay */}
            <div className="card-overlay">
                <div className="card-name-row">
                    <span className="card-name">{persona.name}</span>
                    <span className="card-age">{persona.age}</span>
                    {persona.mbti && <span className="card-mbti">{persona.mbti}</span>}
                </div>
                <div className="card-tags">
                    {(persona.tags || []).map((tag, i) => (
                        <span key={i} className="card-tag">{tag}</span>
                    ))}
                </div>
                <p className="card-bio">{bio}</p>
            </div>

            {/* Swipe indicators */}
            {isTop && (
                <>
                    <motion.div className="swipe-indicator like" style={{ opacity: likeOpacity }}>
                        <span>LIKE</span>
                    </motion.div>
                    <motion.div className="swipe-indicator nope" style={{ opacity: skipOpacity }}>
                        <span>NOPE</span>
                    </motion.div>
                </>
            )}
        </motion.div>
    )
}

export default function Discover() {
    const [personas, setPersonas] = useState([])
    const [currentIndex, setCurrentIndex] = useState(0)
    const [loading, setLoading] = useState(true)
    const navigate = useNavigate()

    useEffect(() => {
        fetchPersonas().then(data => {
            setPersonas(data)
            setLoading(false)
        }).catch(() => setLoading(false))
    }, [])

    const handleSwipe = useCallback((action, persona) => {
        if (action === 'like') {
            navigate(`/chat/${persona.persona_id}`)
        } else {
            setCurrentIndex(prev => prev + 1)
        }
    }, [navigate])

    const visibleCards = personas.slice(currentIndex, currentIndex + 3)

    return (
        <div className="discover-page">
            <div className="bg-orbs" />

            {/* Header */}
            <header className="discover-header">
                <div className="logo gradient-text">✦ OpenHer</div>
            </header>

            {/* Card area */}
            <div className="card-container">
                {loading ? (
                    <div className="state-msg">
                        <div className="spinner" />
                        <p>Discovering...</p>
                    </div>
                ) : visibleCards.length === 0 ? (
                    <div className="state-msg">
                        <span className="state-emoji">💫</span>
                        <h3>All discovered</h3>
                        <button className="btn-pill" onClick={() => setCurrentIndex(0)}>
                            Start Over
                        </button>
                    </div>
                ) : (
                    visibleCards.map((persona, i) => (
                        <SwipeCard
                            key={persona.persona_id}
                            persona={persona}
                            index={i}
                            total={currentIndex + i}
                            onSwipe={handleSwipe}
                            isTop={i === 0}
                        />
                    )).reverse()
                )}
            </div>

            {/* Action buttons */}
            {visibleCards.length > 0 && (
                <div className="actions">
                    <motion.button
                        className="action-circle nope"
                        whileTap={{ scale: 0.85 }}
                        whileHover={{ scale: 1.1 }}
                        onClick={() => handleSwipe('skip', visibleCards[0])}
                    >
                        ✕
                    </motion.button>
                    <motion.button
                        className="action-circle like"
                        whileTap={{ scale: 0.85 }}
                        whileHover={{ scale: 1.1 }}
                        onClick={() => handleSwipe('like', visibleCards[0])}
                    >
                        ♥
                    </motion.button>
                </div>
            )}
        </div>
    )
}
