import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useMotionValue, useTransform, animate } from 'framer-motion'
import { fetchPersonas } from '../services/api'
import './Discover.css'

const GRADIENTS = [
    'linear-gradient(160deg, #2d3a5c 0%, #1a1a30 50%, #2a2040 100%)',
    'linear-gradient(160deg, #3a2d5c 0%, #1a1a30 50%, #2a3040 100%)',
    'linear-gradient(160deg, #2d5c4a 0%, #1a2a30 50%, #203040 100%)',
    'linear-gradient(160deg, #5c3a2d 0%, #301a1a 50%, #403020 100%)',
    'linear-gradient(160deg, #2d4a5c 0%, #1a2030 50%, #303040 100%)',
]

function SwipeCard({ persona, index, onSwipe, isTop, total }) {
    const x = useMotionValue(0)
    const rotate = useTransform(x, [-300, 300], [-15, 15])
    const likeOpacity = useTransform(x, [0, 120], [0, 1])
    const skipOpacity = useTransform(x, [-120, 0], [1, 0])
    const scale = 1 - index * 0.04
    const y = index * 10

    const handleDragEnd = (_, info) => {
        if (info.offset.x > 120) {
            animate(x, 600, { duration: 0.4, ease: 'easeOut' })
            setTimeout(() => onSwipe('like', persona), 350)
        } else if (info.offset.x < -120) {
            animate(x, -600, { duration: 0.4, ease: 'easeOut' })
            setTimeout(() => onSwipe('skip', persona), 350)
        } else {
            animate(x, 0, { type: 'spring', stiffness: 500, damping: 35 })
        }
    }

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
                background: gradient,
            }}
            drag={isTop ? 'x' : false}
            dragConstraints={{ left: 0, right: 0 }}
            dragElastic={0.7}
            onDragEnd={handleDragEnd}
            initial={{ scale: 0.92, opacity: 0 }}
            animate={{ scale, opacity: 1 }}
            transition={{ type: 'spring', stiffness: 300, damping: 25 }}
        >
            {/* Photo placeholder — letter sits in center of entire card */}
            <div className="card-photo-letter">{persona.name?.[0]}</div>

            {/* Gradient fade into info — seamless blend */}
            <div className="card-gradient-fade" />

            {/* Info (overlaid at bottom) */}
            <div className="card-info">
                <div className="card-name-row">
                    <span className="card-name">{persona.name},</span>
                    <span className="card-age">{persona.age}</span>
                    {persona.mbti && <span className="card-mbti">{persona.mbti}</span>}
                </div>
                <div className="card-tags">
                    {(persona.tags || []).map((tag, i) => (
                        <span key={i} className="card-tag">{tag}</span>
                    ))}
                </div>
            </div>

            {/* Swipe stamps */}
            {isTop && (
                <>
                    <motion.div className="swipe-stamp like" style={{ opacity: likeOpacity }}>
                        LIKE
                    </motion.div>
                    <motion.div className="swipe-stamp nope" style={{ opacity: skipOpacity }}>
                        NOPE
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
            <div className="card-area">
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

            {visibleCards.length > 0 && (
                <div className="actions">
                    <motion.button
                        className="action-btn skip"
                        whileTap={{ scale: 0.85 }}
                        whileHover={{ scale: 1.08 }}
                        onClick={() => handleSwipe('skip', visibleCards[0])}
                    >
                        ✕
                    </motion.button>
                    <motion.button
                        className="action-btn like"
                        whileTap={{ scale: 0.85 }}
                        whileHover={{ scale: 1.08 }}
                        onClick={() => handleSwipe('like', visibleCards[0])}
                    >
                        ♥
                    </motion.button>
                </div>
            )}
        </div>
    )
}
