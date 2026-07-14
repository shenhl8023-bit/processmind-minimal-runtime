import sharedStepQuestionProfilesRaw from '../../../docs/配置模板/第三步工序问答共享模板.json?raw'

export interface SharedReasonCategory {
  value: string
  label: string
}

export interface SharedStepQuestionProfile {
  key: string
  pattern: string
  directRootValue?: string
  rootPrompt: string
  rootReasonOrder: string[]
  reasonCategories: SharedReasonCategory[]
}

const parsedProfiles = JSON.parse(sharedStepQuestionProfilesRaw) as SharedStepQuestionProfile[]

export const SHARED_STEP_QUESTION_PROFILES = parsedProfiles

export const SHARED_STEP_QUESTION_PROFILE_BY_KEY = new Map(
  SHARED_STEP_QUESTION_PROFILES.map(profile => [profile.key, profile] as const),
)
