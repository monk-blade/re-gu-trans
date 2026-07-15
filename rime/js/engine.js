/**
 * engine.js — thin Rime adapter entry. Ranking/storage/learning live in modules.
 */
export {
  GujaratiTranslator,
  learnCommittedChoice,
  generateCandidates,
  rankCandidates,
  layoutMenu,
  rankRomanTopTexts,
} from './ranking.js'
