/**
 * engine.js — thin Rime adapter. Ranking/storage/learning live in modules + ime_core.
 */
export {
  GujaratiTranslator,
  learnCommittedChoice,
  generateCandidates,
  rankCandidates,
  layoutMenu,
  rankRomanTopTexts,
} from './ime_core.js'
