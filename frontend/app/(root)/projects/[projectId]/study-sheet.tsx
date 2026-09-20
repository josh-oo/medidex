"use client";

import { StudyDetails } from "@/components/ui/study-view/study-details";
import { useDetailsSheet } from "@/app/context/details-sheet-context";
import { Sheet } from "@/components/ui/sheet";


export default function StudySheet() {

    const {isOpen, study, close} = useDetailsSheet()

    return (
        <Sheet
            open={isOpen}
            onOpenChange={(open) => {
                if (!open){
                    close();
                }
            }}
        >
            <StudyDetails study={study} isActive={isOpen} />
        </Sheet>
    );
}