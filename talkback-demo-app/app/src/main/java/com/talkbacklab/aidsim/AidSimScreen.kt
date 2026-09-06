package com.talkbacklab.aidsim

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.semantics.text
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private fun Modifier.decorative(): Modifier = this.clearAndSetSemantics { }

private fun Modifier.spoken(tag: String, label: String?, display: String): Modifier =
    this.semantics(mergeDescendants = true) {
        testTag = tag
        text = AnnotatedString(display)
        if (label != null) contentDescription = label
    }

@Composable
fun AidSimScreen(state: AidState, onState: (AidState) -> Unit, modifier: Modifier = Modifier) {
    var showVolume by remember { mutableStateOf(false) }
    var showStatus by remember { mutableStateOf(false) }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(AidColors.Background)
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
    ) {
        TopBar(state) { showStatus = !showStatus }
        Banner()
        ProgramCard(state, onState)
        MasterVolumeRow(state) { showVolume = !showVolume }
        if (showVolume) VolumePanel(state, onState)
        if (showStatus) StatusPanel(state)
        Spacer(Modifier.height(16.dp))
        BottomNav()
    }
}

@Composable
private fun TopBar(state: AidState, onOpenStatus: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            "AidSim",
            color = AidColors.TextPrimary,
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.semantics { testTag = "brand" }
        )
        Spacer(Modifier.weight(1f))
        // INTENTIONAL ACCESSIBILITY DEFECT 1:
        // The left battery stays fully visible and tappable, but skipA11y removes its
        // whole subtree from the semantics tree. It never takes accessibility focus and
        // is never announced, so meaningful visual information has no accessible
        // equivalent. The right chip is deliberately left reachable for contrast.
        BatteryChip("chip_battery_left", "L", state.leftBattery, AidColors.Left,
            Labels.batteryChip(state, Side.LEFT), onOpenStatus,
            skipA11y = A11yDefects.active(state))
        Spacer(Modifier.width(12.dp))
        BatteryChip("chip_battery_right", "R", state.rightBattery, AidColors.Right,
            Labels.batteryChip(state, Side.RIGHT), onOpenStatus)
    }
}

@Composable
private fun BatteryChip(
    tag: String,
    side: String,
    value: Int,
    tint: Color,
    label: String?,
    onClick: () -> Unit,
    skipA11y: Boolean = false
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .then(if (skipA11y) Modifier.decorative() else Modifier)
            .clip(RoundedCornerShape(10.dp))
            .background(AidColors.Surface)
            .clickable { onClick() }
            .padding(horizontal = 10.dp, vertical = 6.dp)
    ) {
        Text(
            side, color = tint, fontSize = 13.sp, fontWeight = FontWeight.Bold,
            modifier = Modifier.decorative()
        )
        Spacer(Modifier.width(6.dp))
        Text(
            "$value%", color = AidColors.TextPrimary, fontSize = 13.sp,
            modifier = Modifier.spoken(tag, label, "$value%")
        )
    }
}

@Composable
private fun Banner() {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .background(AidColors.Banner)
            .padding(vertical = 6.dp)
            .semantics { testTag = "banner_simulation" },
        contentAlignment = Alignment.Center
    ) {
        Text("Simulation Mode", color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.Medium)
    }
}

private val PROGRAMS = listOf("Universal", "Noisy", "Restaurant", "Music")

@Composable
private fun ProgramCard(state: AidState, onState: (AidState) -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp)
            .clip(RoundedCornerShape(18.dp))
            .background(AidColors.Surface)
            .padding(20.dp)
    ) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            Text(
                "Programs",
                color = AidColors.TextPrimary,
                fontSize = 14.sp,
                modifier = Modifier
                    .spoken("programs_button", Labels.programsButton(state), "Programs")
                    .clip(RoundedCornerShape(14.dp))
                    .background(AidColors.SurfaceHigh)
                    .clickable {
                        val next = PROGRAMS[(PROGRAMS.indexOf(state.program) + 1) % PROGRAMS.size]
                        onState(state.copy(program = next, programDescription = describe(next)))
                    }
                    .padding(horizontal = 14.dp, vertical = 8.dp)
            )
        }
        Spacer(Modifier.height(28.dp))
        Column {
            Text(
                state.program,
                color = AidColors.TextPrimary,
                fontSize = 34.sp,
                lineHeight = 40.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.spoken("program_name", Labels.program(state), state.program)
            )
            Spacer(Modifier.height(8.dp))
            Text(state.programDescription, color = AidColors.TextSecondary, fontSize = 15.sp)
        }
        Spacer(Modifier.height(36.dp))
    }
}

private fun describe(program: String): String = when (program) {
    "Noisy" -> "Reduces background noise in busy places."
    "Restaurant" -> "Focuses on speech in front of you."
    "Music" -> "Widens the range for listening to music."
    else -> "Personal program adapting to your environment."
}

@Composable
private fun MasterVolumeRow(state: AidState, onOpenVolume: () -> Unit) {
    val average = (state.leftVolume + state.rightVolume) / 2
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp)
            .clip(RoundedCornerShape(16.dp))
            .background(AidColors.Surface)
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.weight(1f)
        ) {
            Text(
                "Volume", color = AidColors.TextSecondary, fontSize = 14.sp,
                modifier = Modifier.decorative()
            )
            Spacer(Modifier.width(12.dp))
            Track(average, AidColors.Accent, Modifier.weight(1f))
            Spacer(Modifier.width(12.dp))
            Text(
                Labels.displayNumber(average),
                color = AidColors.TextPrimary,
                fontSize = 16.sp,
                modifier = Modifier.spoken(
                    "master_volume",
                    Labels.masterVolume(state),
                    Labels.displayNumber(average)
                )
            )
        }
        Spacer(Modifier.width(12.dp))
        Text(
            "L|R",
            color = AidColors.TextPrimary,
            fontSize = 14.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier
                .spoken("open_volume_panel", Labels.volumePanelButton(state), "L|R")
                .clip(RoundedCornerShape(10.dp))
                .background(AidColors.SurfaceHigh)
                .clickable { onOpenVolume() }
                .padding(horizontal = 12.dp, vertical = 8.dp)
        )
    }
}

@Composable
private fun Track(value: Int, tint: Color, modifier: Modifier = Modifier) {
    val span = (AidState.VOLUME_MAX - AidState.VOLUME_MIN).toFloat()
    val fraction = ((value - AidState.VOLUME_MIN) / span).coerceIn(0f, 1f)
    Box(
        modifier = modifier
            .height(20.dp),
        contentAlignment = Alignment.CenterStart
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .height(4.dp)
                .clip(CircleShape)
                .background(AidColors.SurfaceHigh)
        )
        Box(
            Modifier
                .fillMaxWidth(fraction)
                .height(4.dp)
                .clip(CircleShape)
                .background(tint)
        )
        Box(
            Modifier
                .fillMaxWidth(fraction)
                .height(20.dp),
            contentAlignment = Alignment.CenterEnd
        ) {
            Box(
                Modifier
                    .size(18.dp)
                    .clip(CircleShape)
                    .background(tint)
            )
        }
    }
}

@Composable
private fun VolumePanel(state: AidState, onState: (AidState) -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp)
            .clip(RoundedCornerShape(18.dp))
            .background(AidColors.Surface)
            .padding(20.dp)
    ) {
        Text("Volume", color = AidColors.TextPrimary, fontSize = 20.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(6.dp))
        Text(
            "You can adjust the volume of each hearing aid separately.",
            color = AidColors.TextSecondary,
            fontSize = 14.sp
        )
        Spacer(Modifier.height(20.dp))
        VolumeRow("volume_left", "Left", state.leftVolume, AidColors.Left,
            Labels.volume(state, Side.LEFT)) {
            onState(state.copy(leftVolume = it))
        }
        Spacer(Modifier.height(24.dp))
        VolumeRow("volume_right", "Right", state.rightVolume, AidColors.Right,
            Labels.volume(state, Side.RIGHT)) {
            onState(state.copy(rightVolume = it))
        }
    }
}

@Composable
private fun VolumeRow(
    tag: String,
    side: String,
    value: Int,
    tint: Color,
    label: String?,
    onChange: (Int) -> Unit
) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                side, color = AidColors.TextSecondary, fontSize = 15.sp,
                modifier = Modifier.decorative()
            )
            Spacer(Modifier.weight(1f))
            Text(
                Labels.displayNumber(value),
                color = AidColors.TextPrimary,
                fontSize = 32.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.spoken(tag, label, Labels.displayNumber(value))
            )
        }
        Spacer(Modifier.height(8.dp))
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            StepButton("${tag}_minus", "Decrease $side volume", "-") {
                onChange((value - 1).coerceAtLeast(AidState.VOLUME_MIN))
            }
            Spacer(Modifier.width(12.dp))
            Track(value, tint, Modifier.weight(1f))
            Spacer(Modifier.width(12.dp))
            StepButton("${tag}_plus", "Increase $side volume", "+") {
                onChange((value + 1).coerceAtMost(AidState.VOLUME_MAX))
            }
        }
    }
}

@Composable
private fun StepButton(tag: String, label: String, glyph: String, onClick: () -> Unit) {
    Text(
        glyph,
        color = AidColors.TextPrimary,
        fontSize = 20.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier
            .spoken(tag, label, glyph)
            .clip(CircleShape)
            .background(AidColors.SurfaceHigh)
            .clickable { onClick() }
            .padding(horizontal = 14.dp, vertical = 6.dp)
    )
}

@Composable
private fun StatusPanel(state: AidState) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp)
            .clip(RoundedCornerShape(18.dp))
            .background(AidColors.Surface)
            .padding(20.dp)
    ) {
        Text(
            "Hearing aid status",
            color = AidColors.TextPrimary,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold
        )
        Spacer(Modifier.height(20.dp))
        Row(modifier = Modifier.fillMaxWidth()) {
            StatusCard(
                "status_left", "Left", state.leftConnected, state.leftBattery, AidColors.Left,
                Labels.connection(state, Side.LEFT), Labels.battery(state, Side.LEFT),
                Modifier.weight(1f), exposeDecorative = A11yDefects.active(state)
            )
            Spacer(Modifier.width(16.dp))
            StatusCard(
                "status_right", "Right", state.rightConnected, state.rightBattery, AidColors.Right,
                Labels.connection(state, Side.RIGHT), Labels.battery(state, Side.RIGHT),
                Modifier.weight(1f), exposeDecorative = A11yDefects.active(state)
            )
        }
    }
}

@Composable
private fun StatusCard(
    tag: String,
    side: String,
    connected: Boolean,
    battery: Int,
    tint: Color,
    connectionLabel: String?,
    batteryLabel: String?,
    modifier: Modifier = Modifier,
    exposeDecorative: Boolean = false
) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(14.dp))
            .background(AidColors.SurfaceHigh)
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            side,
            color = Color.White,
            fontSize = 13.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier
                .clip(RoundedCornerShape(10.dp))
                .background(tint)
                .padding(horizontal = 12.dp, vertical = 4.dp)
        )
        Spacer(Modifier.height(12.dp))
        Row(
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // INTENTIONAL ACCESSIBILITY DEFECT 5 (first half):
            // A purely decorative status dot is given a label describing its colour and
            // shape, adding noise that carries no information.
            Box(
                Modifier
                    .then(
                        if (exposeDecorative) {
                            Modifier.spoken(
                                "${tag}_indicator",
                                A11yDefects.STATUS_INDICATOR_DECORATIVE,
                                ""
                            )
                        } else {
                            Modifier
                        }
                    )
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(if (connected) AidColors.Connected else AidColors.TextSecondary)
            )
            Spacer(Modifier.width(8.dp))
            Text(
                if (connected) "Connected" else "Disconnected",
                color = AidColors.TextPrimary,
                fontSize = 14.sp,
                modifier = Modifier.spoken(
                    "${tag}_connection",
                    connectionLabel,
                    if (connected) "Connected" else "Disconnected"
                )
            )
        }
        Spacer(Modifier.height(10.dp))
        // INTENTIONAL ACCESSIBILITY DEFECT 5 (second half):
        // The battery percentage - the meaningful value on this card - is removed from
        // the semantics tree entirely while the decorative dot above is announced. The
        // priority is exactly inverted.
        Text(
            "$battery%",
            color = AidColors.TextPrimary,
            fontSize = 24.sp,
            fontWeight = FontWeight.Bold,
            modifier = if (exposeDecorative) {
                Modifier.decorative()
            } else {
                Modifier.spoken("${tag}_battery", batteryLabel, "$battery%")
            }
        )
    }
}

@Composable
private fun BottomNav() {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 12.dp),
        horizontalArrangement = Arrangement.SpaceEvenly
    ) {
        Text(
            "Home",
            color = AidColors.Accent,
            fontSize = 13.sp,
            modifier = Modifier.spoken("nav_home", "Home, selected", "Home")
        )
        Text(
            "More",
            color = AidColors.TextSecondary,
            fontSize = 13.sp,
            modifier = Modifier.spoken("nav_more", "More", "More")
        )
    }
}
