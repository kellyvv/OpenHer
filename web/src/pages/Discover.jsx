import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useMotionValue, useTransform, animate } from 'framer-motion'
import { fetchPersonas } from '../services/api'
import './Discover.css'

function SwipeCard({ persona, onSwipe, style, isTop }) {
    const x = useMotionValue(0)
    const rotate = useTransform(x, [-200, 200], [-15, 15])
    const likeOpacity = useTransform(x, [0, 100], [0, 1])
    const skipOpacity = useTransform(x, [-100, 0], [1, 0])

    const handleDragEnd = (_, info) => {
        if (info.offset.x > 100) {
            animate(x, 500, { duration: 0.3 })
            setTimeout(() => onSwipe('like', persona), 300)
        } else if (info.offset.x < -100) {
            animate(x, -500, { duration: 0.3 })
            setTimeout(() => onSwipe('skip', persona), 300)
        } else {
            animate(x, 0, { type: 'spring', stiffness: 500, damping: 30 })
        }
    }

    const bio = typeof persona.bio === 'object'
        ? (persona.bio.en || persona.bio.zh || '')
        : (persona.bio || '')

    return (
        <motion.div
            className="swipe-card"
            style={{ x, rotate, ...style }}
            drag={isTop ? 'x' : false}
            dragConstraints={{ left: 0, right: 0 }}
            dragElastic={0.8}
            onDragEnd={handleDragEnd}
            whileTap={{ cursor: 'grabbing' }}
        >
            {/* Gradient avatar placeholder */}
            <div className="card-avatar">
                <div className="card-avatar-gradient">
                    <span className="card-avatar-letter">{persona.name?.[0] || '?'}</span>
                </div>
            </div>

            {/* Info */}
            <div className="card-info">
                <div className="card-name-row">
                    <h2 className="card-name">{persona.name}</h2>
                    <span className="card-age">{persona.age}</span>
                    {persona.mbti && <span className="card-mbti">{persona.mbti}</span>}
                </div>
                <p className="card-bio">{bio}</p>
                <div className="card-tags">
                    {(persona.tags || []).map((tag, i) => (
                        <span key={i} className="card-tag">{tag}</span>
                    ))}
                </div>
            </div>

            {/* Swipe indicators */}
            {isTop && (
                <>
                    <motion.div className="swipe-label like" style={{ opacity: likeOpacity }}>
                        LIKE ♥
                    </motion.div>
                    <motion.div className="swipe-label skip" style={{ opacity: skipOpacity }}>
                        SKIP ✕
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

    const handleSwipe = (action, persona) => {
        if (action === 'like') {
            navigate(`/chat/${persona.persona_id}`)
        } else {
            setCurrentIndex(prev => prev + 1)
        }
    }

    const visibleCards = personas.slice(currentIndex, currentIndex + 3)

    return (
        <div className="discover-page">
            <div className="bg-orbs" />

            <header className="discover-header">
                <h1 className="gradient-text">✦ OpenHer</h1>
                <p>Swipe to discover your AI companion</p>
            </header>

            <div className="card-stack">
                {loading ? (
                    <div className="loading-state">
                        <div className="loading-spinner" />
                        <p>Loading companions...</p>
                    </div>
                ) : visibleCards.length === 0 ? (
                    <div className="empty-state">
                        <span className="empty-emoji">💫</span>
                        <h3>No more cards</h3>
                        <p>All companions discovered!</p>
                        <button
                            className="btn-reset"
                            onClick={() => setCurrentIndex(0)}
                        >
                            Start Over
                        </button>
                    </div>
                ) : (
                    visibleCards.map((persona, i) => (
                        <SwipeCard
                            key={persona.persona_id}
                            persona={persona}
                            onSwipe={handleSwipe}
                            isTop={i === 0}
                            style={{
                                zIndex: 3 - i,
                                scale: 1 - i * 0.05,
                                y: i * 12,
                            }}
                        />
                    )).reverse()
                )}
            </div>

            {visibleCards.length > 0 && (
                <div className="action-buttons">
                    <button
                        className="action-btn skip-btn"
                        onClick={() => handleSwipe('skip', visibleCards[0])}
                    >
                        ✕
                    </button>
                    <button
                        className="action-btn like-btn"
                        onClick={() => handleSwipe('like', visibleCards[0])}
                    >
                        ♥
                    </button>
                </div>
            )}
        </div>
    )
}
