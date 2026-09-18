// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title CoreAnchor
 * @notice Minimal hash notarization contract for CORE artefacts.
 *
 * CORE validates and fingerprints off-chain.
 * This contract only records submitted hashes.
 * The chain does not decide whether the artefact is valid.
 *
 * Principle: off-chain data + on-chain hash
 * CORE remains the authority for validation, replay, and certification.
 */
contract CoreAnchor {

    // ─── Events ──────────────────────────────────────────────────────────

    event HashAnchored(
        address indexed anchorer,
        bytes32 indexed dataHash,
        uint256 indexed timestamp
    );

    // ─── Storage ─────────────────────────────────────────────────────────

    /// @notice Maps a submitted hash to the block timestamp of its first anchoring.
    mapping(bytes32 => uint256) public anchoredAt;

    /// @notice Maps a submitted hash to the address that first anchored it.
    mapping(bytes32 => address) public anchoredBy;

    /// @notice Total number of unique hashes anchored.
    uint256 public totalAnchored;

    // ─── Access ──────────────────────────────────────────────────────────

    address public owner;

    modifier onlyOwner() {
        require(msg.sender == owner, "CoreAnchor: not owner");
        _;
    }

    // ─── Constructor ─────────────────────────────────────────────────────

    constructor() {
        owner = msg.sender;
    }

    // ─── Core Function ───────────────────────────────────────────────────

    /**
     * @notice Notarize a canonical hash on-chain.
     *
     * Requirements:
     * - dataHash must not be zero (fail-closed).
     * - dataHash must not have been anchored before (idempotency).
     *
     * The contract stores only the hash, the anchorer address, and the
     * block timestamp. No CORE validation logic, replay logic, audit
     * logic, or private-domain logic belongs in this contract.
     *
     * @param dataHash The canonical bytes32 hash of a frozen CORE artefact.
     */
    function notarizeHash(bytes32 dataHash) external {
        require(dataHash != bytes32(0), "CoreAnchor: zero hash rejected");
        require(anchoredAt[dataHash] == 0, "CoreAnchor: hash already anchored");

        anchoredAt[dataHash] = block.timestamp;
        anchoredBy[dataHash] = msg.sender;
        totalAnchored += 1;

        emit HashAnchored(msg.sender, dataHash, block.timestamp);
    }

    // ─── Read Functions ──────────────────────────────────────────────────

    /**
     * @notice Check whether a hash has been anchored.
     */
    function isAnchored(bytes32 dataHash) external view returns (bool) {
        return anchoredAt[dataHash] > 0;
    }

    /**
     * @notice Get the anchoring record for a hash.
     * @return timestamp The block timestamp when anchored (0 if never).
     * @return anchorer  The address that anchored it (address(0) if never).
     */
    function getAnchor(bytes32 dataHash) external view returns (
        uint256 timestamp,
        address anchorer
    ) {
        return (anchoredAt[dataHash], anchoredBy[dataHash]);
    }

    // ─── Admin ───────────────────────────────────────────────────────────

    /**
     * @notice Transfer contract ownership.
     * No other admin functions exist. The contract is intentionally
     * small and does not support pausing, upgrading, or fee changes.
     */
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "CoreAnchor: zero address rejected");
        owner = newOwner;
    }
}
