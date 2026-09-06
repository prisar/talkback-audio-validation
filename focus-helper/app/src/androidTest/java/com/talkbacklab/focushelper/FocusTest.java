package com.talkbacklab.focushelper;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.UiAutomation;
import android.os.Bundle;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.Test;
import org.junit.runner.RunWith;

import java.util.List;

/**
 * Moves TalkBack's accessibility focus to a node by resource-id, using the
 * same AccessibilityNodeInfo API an AccessibilityService uses, not a
 * simulated touch. Invoked headless via `adb shell am instrument`.
 *
 * Required instrumentation args: target_package, resource_id.
 */
@RunWith(AndroidJUnit4.class)
public class FocusTest {

    @Test
    public void focusByResourceId() {
        Bundle args = InstrumentationRegistry.getArguments();
        String targetPackage = args.getString("target_package");
        String resourceId = args.getString("resource_id");
        if (targetPackage == null || resourceId == null) {
            throw new AssertionError("MISSING_ARGS: need target_package and resource_id");
        }

        boolean keepTalkBackAlive = !"1".equals(args.getString("suppress_others"));
        UiAutomation automation =
                keepTalkBackAlive
                        ? InstrumentationRegistry.getInstrumentation()
                                .getUiAutomation(
                                        UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES)
                        : InstrumentationRegistry.getInstrumentation().getUiAutomation();
        AccessibilityServiceInfo info = automation.getServiceInfo();
        info.flags |= AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
        automation.setServiceInfo(info);

        AccessibilityNodeInfo node = null;
        for (int attempt = 0; attempt < 10 && node == null; attempt++) {
            node = findByViewId(automation, targetPackage, resourceId);
            if (node == null) {
                sleep(300);
            }
        }
        if (node == null) {
            throw new AssertionError("NODE_NOT_FOUND: " + resourceId + " in " + targetPackage);
        }

        boolean ok = performFocus(node);
        if (!ok) {
            AccessibilityWindowInfo window = node.getWindow();
            throw new AssertionError(
                    "FOCUS_ACTION_FAILED: "
                            + resourceId
                            + " visible="
                            + node.isVisibleToUser()
                            + " focusable="
                            + node.isFocusable()
                            + " important="
                            + node.isImportantForAccessibility()
                            + " windowActive="
                            + (window != null && window.isActive())
                            + " windowFocused="
                            + (window != null && window.isFocused())
                            + " windowId="
                            + (window != null ? window.getId() : "null"));
        }
    }

    /** Diagnostic: is UiAutomation able to perform ANY action on this
     * device at all, or is accessibility-focus specifically blocked? */
    @Test
    public void clickByResourceId() {
        Bundle args = InstrumentationRegistry.getArguments();
        String targetPackage = args.getString("target_package");
        String resourceId = args.getString("resource_id");
        UiAutomation automation =
                InstrumentationRegistry.getInstrumentation()
                        .getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        AccessibilityServiceInfo info = automation.getServiceInfo();
        info.flags |= AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
        automation.setServiceInfo(info);
        AccessibilityNodeInfo node = findByViewId(automation, targetPackage, resourceId);
        if (node == null) {
            throw new AssertionError("NODE_NOT_FOUND: " + resourceId);
        }
        boolean ok = node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
        if (!ok) {
            throw new AssertionError("CLICK_ACTION_FAILED: " + resourceId);
        }
    }

    /** Retries the action itself: the first attempt on a freshly-queried
     * node can still race a Compose recomposition and report a stale-node
     * failure without throwing. */
    private boolean performFocus(AccessibilityNodeInfo node) {
        int action = AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS;
        for (int attempt = 0; attempt < 3; attempt++) {
            if (node.performAction(action)) {
                return true;
            }
            sleep(200);
        }
        return false;
    }

    private AccessibilityNodeInfo findByViewId(
            UiAutomation automation, String targetPackage, String resourceId) {
        for (AccessibilityWindowInfo window : automation.getWindows()) {
            AccessibilityNodeInfo root = window.getRoot();
            AccessibilityNodeInfo found = queryRoot(root, targetPackage, resourceId);
            if (found != null) {
                return found;
            }
        }
        return queryRoot(automation.getRootInActiveWindow(), targetPackage, resourceId);
    }

    /** Compose exposes testTagsAsResourceId tags as a bare string with no
     * "package:id/" prefix, so findAccessibilityNodeInfosByViewId (which
     * expects that prefixed form) never matches them; walk the tree instead. */
    private AccessibilityNodeInfo queryRoot(
            AccessibilityNodeInfo node, String targetPackage, String resourceId) {
        if (node == null) {
            return null;
        }
        String viewId = node.getViewIdResourceName();
        boolean idMatches = viewId != null && viewId.endsWith(resourceId);
        boolean packageMatches =
                node.getPackageName() != null
                        && node.getPackageName().toString().equals(targetPackage);
        if (idMatches && packageMatches) {
            return node;
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo found = queryRoot(node.getChild(i), targetPackage, resourceId);
            if (found != null) {
                return found;
            }
        }
        return null;
    }

    private void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException ignored) {
        }
    }
}
