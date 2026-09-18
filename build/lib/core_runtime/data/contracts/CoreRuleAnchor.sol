// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title CoreRuleAnchor
 * @notice Minimal, non-custodial timestamping for CORE frozen-rule batches.
 *
 * CORE validates rule content, private commitments, approvals, and Merkle
 * proofs off-chain. This contract records only a Merkle root and its manifest
 * hash. It does not decide whether a rule is good, execute a rule, hold funds,
 * issue a token, collect a fee, or grant administrative authority.
 *
 * General rules may be published off-chain. Personal rules remain private and
 * contribute only a blinded commitment to the Merkle root.
 */
contract CoreRuleAnchor {
    /**
     * @dev visibilityMask bit 0 means at least one public rule set; bit 1
     * means at least one private commitment. Valid values are 1, 2, and 3.
     */
    event RuleBatchAnchored(
        address indexed anchorer,
        bytes32 indexed merkleRoot,
        bytes32 indexed manifestHash,
        uint32 ruleCount,
        uint8 visibilityMask,
        uint256 timestamp
    );

    /**
     * @notice One storage slot per unique root keeps recurring anchor cost low.
     * The event is the source for anchorer, count, visibility, and timestamp.
     */
    mapping(bytes32 merkleRoot => bytes32 manifestHash) public manifestByRoot;

    /**
     * @notice Anchor one validated batch. The caller's transaction signature
     * identifies the anchorer but does not replace CORE approval validation.
     */
    function anchorRuleBatch(
        bytes32 merkleRoot,
        bytes32 manifestHash,
        uint32 ruleCount,
        uint8 visibilityMask
    ) external {
        require(merkleRoot != bytes32(0), "CoreRuleAnchor: zero root");
        require(manifestHash != bytes32(0), "CoreRuleAnchor: zero manifest");
        require(ruleCount > 0, "CoreRuleAnchor: empty batch");
        require(
            visibilityMask > 0 && visibilityMask <= 3,
            "CoreRuleAnchor: invalid visibility"
        );
        require(
            manifestByRoot[merkleRoot] == bytes32(0),
            "CoreRuleAnchor: root already anchored"
        );

        manifestByRoot[merkleRoot] = manifestHash;

        emit RuleBatchAnchored(
            msg.sender,
            merkleRoot,
            manifestHash,
            ruleCount,
            visibilityMask,
            block.timestamp
        );
    }

    /** @notice Return true only when the exact root is already anchored. */
    function isAnchored(bytes32 merkleRoot) external view returns (bool) {
        return manifestByRoot[merkleRoot] != bytes32(0);
    }
}
