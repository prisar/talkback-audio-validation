package com.talkbacklab.aidsim

import kotlin.math.abs

enum class Side { LEFT, RIGHT }

// INTENTIONAL ACCESSIBILITY DEFECT SUITE:
// Used for testing the AI accessibility detection bot. Every string and rule below
// exists to produce a specific, detectable accessibility fault while leaving the
// visible UI correct. Do not "fix" these; they are the test subject.
// Active only when the app is launched with `--es defect a11y_suite`, so the
// default build keeps a clean, correct accessibility baseline to compare against.
object A11yDefects {

    fun active(state: AidState): Boolean = state.defect == Defect.A11Y_SUITE

    // Defect 2 - missing accessible information: percentage omitted from the announcement.
    const val RIGHT_BATTERY_INCOMPLETE = "Battery"

    // Defect 3 - incorrect accessible information: label contradicts the control.
    const val PROGRAMS_WRONG_LABEL = "Increase volume"

    // Defect 4 - unclear actionable semantics: names no action and no target.
    const val VOLUME_PANEL_UNCLEAR_LABEL = "Button"

    // Defect 5 - decorative information exposed in place of meaningful information.
    const val STATUS_INDICATOR_DECORATIVE = "Blue circle icon"
}

object Labels {

    private fun sideWord(side: Side) = if (side == Side.LEFT) "Left" else "Right"

    private fun batteryValue(state: AidState, side: Side): Int {
        val base = when (effectiveSide(state, side)) {
            Side.LEFT -> state.leftBattery
            Side.RIGHT -> state.rightBattery
        }
        return if (state.defect == Defect.BATTERY_VALUE) {
            if (base >= 30) base - 30 else base + 30
        } else {
            base
        }
    }

    private fun volumeValue(state: AidState, side: Side): Int {
        val base = when (effectiveSide(state, side)) {
            Side.LEFT -> state.leftVolume
            Side.RIGHT -> state.rightVolume
        }
        return if (state.defect == Defect.VOLUME_SIGN) abs(base) else base
    }

    private fun connectedValue(state: AidState, side: Side): Boolean =
        when (effectiveSide(state, side)) {
            Side.LEFT -> state.leftConnected
            Side.RIGHT -> state.rightConnected
        }

    private fun effectiveSide(state: AidState, side: Side): Side =
        if (state.defect == Defect.SWAP_SIDES) {
            if (side == Side.LEFT) Side.RIGHT else Side.LEFT
        } else {
            side
        }

    private fun spokenNumber(value: Int): String =
        if (value < 0) "minus ${abs(value)}" else "$value"

    fun battery(state: AidState, side: Side): String? {
        if (state.defect == Defect.MISSING_LABEL) return null
        return "${sideWord(side)} hearing aid battery, ${batteryValue(state, side)} percent"
    }

    fun batteryChip(state: AidState, side: Side): String? {
        if (state.defect == Defect.MISSING_LABEL) return null
        // INTENTIONAL ACCESSIBILITY DEFECT 2:
        // The right battery renders "R 85%" but announces only "Battery". The
        // percentage - the entire point of the control - never reaches the user.
        if (A11yDefects.active(state) && side == Side.RIGHT) {
            return A11yDefects.RIGHT_BATTERY_INCOMPLETE
        }
        return "${sideWord(side)} battery, ${batteryValue(state, side)} percent"
    }

    // INTENTIONAL ACCESSIBILITY DEFECT 3:
    // Visually "Programs"; announced as "Increase volume". The label describes a
    // different control entirely, so a screen reader user cannot find the real one.
    fun programsButton(state: AidState): String =
        if (A11yDefects.active(state)) A11yDefects.PROGRAMS_WRONG_LABEL
        else "Programs, change program"

    // INTENTIONAL ACCESSIBILITY DEFECT 4:
    // Stays clickable and functional, but the label names neither the action nor
    // its target, so the control's purpose is unknowable without sight.
    fun volumePanelButton(state: AidState): String =
        if (A11yDefects.active(state)) A11yDefects.VOLUME_PANEL_UNCLEAR_LABEL
        else "Adjust left and right volume separately"

    fun volume(state: AidState, side: Side): String? {
        if (state.defect == Defect.MISSING_LABEL) return null
        return "${sideWord(side)} volume, level ${spokenNumber(volumeValue(state, side))}"
    }

    fun connection(state: AidState, side: Side): String? {
        if (state.defect == Defect.MISSING_LABEL) return null
        val word = if (connectedValue(state, side)) "connected" else "disconnected"
        return "${sideWord(side)} hearing aid, $word"
    }

    fun program(state: AidState): String? {
        if (state.defect == Defect.MISSING_LABEL) return null
        return "Program, ${state.program}, selected"
    }

    fun masterVolume(state: AidState): String? {
        if (state.defect == Defect.MISSING_LABEL) return null
        val average = (state.leftVolume + state.rightVolume) / 2
        return "Volume, level ${spokenNumber(average)}"
    }

    fun displayNumber(value: Int): String = "$value"
}
