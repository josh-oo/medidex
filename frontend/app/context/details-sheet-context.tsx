"use client"

import { StudyDto } from "@/types/apiDTOs"
import { createContext, useContext, useState, type ReactNode } from "react"


type ContextType = {
  openWithStudyItem: (study: StudyDto) => void
  openWithStudyId: (studyId: number) => void
  close: () => void
  isOpen: boolean
  study: StudyDto | null
  loading: boolean
}

const DetailsSheetContext = createContext<ContextType | null>(null)

type DetailsSheetProviderProps = {
  children: ReactNode
}

export function DetailsSheetProvider({ children }: DetailsSheetProviderProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [study, setStudy] = useState<StudyDto | null>(null)
  const [loading, setLoading] = useState(false)

  async function openWithStudyId(studyId: number) {
    setIsOpen(true)
    setLoading(true)
    setStudy(null)

    const res = await fetch(`/api/meerkat/studies/${studyId}`, { cache: "no-store" })
    const data = await res.json()


    setStudy(data)
    setLoading(false)
  }

  function openWithStudyItem(study: StudyDto) {
    setStudy(study)
    setIsOpen(true)
  }

  function close() {
    setIsOpen(false)
  }

  return (
    <DetailsSheetContext.Provider
      value={{ openWithStudyItem, openWithStudyId, close, isOpen, study, loading }}
    >
      {children}
    </DetailsSheetContext.Provider>
  )
}

export function useDetailsSheet() {
  const ctx = useContext(DetailsSheetContext)
  if (!ctx) throw new Error("Must be used inside provider")
  return ctx
}